"""
example cmdline:

python test/reproduction/so/benchmark_so_botorch_math.py --problem branin --n 200 --init 10 --refit 1 --rep 1 --start_id 0

"""
import os
import sys
import time
import numpy as np
import argparse
import pickle as pkl

#sys.path.insert(0, '../botorch/')   # for dev

sys.path.insert(0, os.getcwd())
from test.reproduction.so.so_benchmark_function import get_problem
from test.reproduction.test_utils import timeit, seeds

parser = argparse.ArgumentParser()
parser.add_argument('--problem', type=str)
parser.add_argument('--n', type=int, default=100)
parser.add_argument('--init', type=int, default=10)
parser.add_argument('--refit', type=int, default=1)
parser.add_argument('--rep', type=int, default=1)
parser.add_argument('--start_id', type=int, default=0)

args = parser.parse_args()
problem_str = args.problem
max_runs = args.n
initial_runs = args.init
refit = args.refit
rep = args.rep
start_id = args.start_id
mth = 'botorch'

import torch
from botorch.models import SingleTaskGP
from botorch.models.transforms.outcome import Standardize
from botorch.utils.transforms import unnormalize
from gpytorch.mlls import ExactMarginalLogLikelihood
from botorch import fit_gpytorch_model
from botorch.acquisition import ExpectedImprovement
from botorch.optim import optimize_acqf
from botorch.exceptions import BadInitialCandidatesWarning
import warnings

warnings.filterwarnings('ignore', category=BadInitialCandidatesWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)

tkwargs = {
    "dtype": torch.double,
    "device": torch.device("cuda" if torch.cuda.is_available() else "cpu"),
}

problem = get_problem(problem_str)
# Caution: all train_x in [0, 1]. unnormalize in objective funtion and when saving
# Caution: botorch maximize the objective function
problem_bounds = torch.tensor(problem.bounds, **tkwargs).transpose(-1, -2)  # caution
standard_bounds = torch.tensor([[0.0] * problem.dim,
                                [1.0] * problem.dim], **tkwargs)


# ===== botorch helper functions =====

def generate_initial_data(init_num, obj_func, time_list, global_start_time):
    # generate training data
    train_x = torch.rand(init_num, problem.dim, **tkwargs)  # caution: train_x in [0, 1]
    train_obj = []
    for x in train_x:
        y = obj_func(x)
        train_obj.append(y)
        global_time = time.time() - global_start_time
        time_list.append(global_time)
    train_obj = torch.tensor(train_obj, **tkwargs).reshape(init_num, -1)
    return train_x, train_obj


def initialize_model(train_x, train_obj, state_dict=None):
    # define models for objective and constraint
    #model = SingleTaskGP(train_x, train_obj)
    model = SingleTaskGP(train_x, train_obj, outcome_transform=Standardize(m=train_obj.shape[-1]))
    mll = ExactMarginalLogLikelihood(model.likelihood, model)
    # load state dict if it is passed
    if state_dict is not None:
        model.load_state_dict(state_dict)
    return mll, model


def optimize_acqf_and_get_observation(acq_func, obj_func, time_list, global_start_time):
    """Optimizes the acquisition function, and returns a new candidate and observation."""
    # optimize
    candidates, _ = optimize_acqf(
        acq_function=acq_func,
        bounds=standard_bounds,
        q=1,
        num_restarts=20,
        raw_samples=1024,
        options={"batch_limit": 5, "maxiter": 200},
    )
    # observe new values
    new_x = candidates.detach()
    new_obj = []
    for x in new_x:
        y = obj_func(x)
        new_obj.append(y)
        global_time = time.time() - global_start_time
        time_list.append(global_time)
    new_obj = torch.tensor(new_obj, **tkwargs).reshape(new_x.shape[0], -1)
    print(f'evaluate {new_x.shape[0]} configs on real objective')
    return new_x, new_obj

# ===== end of botorch helper functions =====


def evaluate(mth, run_i, seed):
    print(mth, run_i, seed, '===== start =====', flush=True)

    def objective_function(x: torch.Tensor):
        # Caution: unnormalize and maximize
        x = unnormalize(x, bounds=problem_bounds)
        x = x.cpu().numpy().astype(np.float64)      # caution
        y = problem.evaluate(x)
        return -y

    time_list = []
    global_start_time = time.time()

    # random seed
    np.random.seed(seed)
    torch.manual_seed(seed)

    # call helper functions to generate initial training data and initialize model
    train_x, train_obj = generate_initial_data(initial_runs, objective_function, time_list, global_start_time)
    mll, model = initialize_model(train_x, train_obj)

    # run (max_runs - initial_runs) rounds of BayesOpt after the initial random batch
    for iteration in range(initial_runs + 1, max_runs + 1):
        t0 = time.time()
        # fit the models
        fit_gpytorch_model(mll)
        # define EI acquisition modules
        best_value = train_obj.max()
        EI = ExpectedImprovement(model=model, best_f=best_value)
        # optimize and get new observation
        new_x, new_obj = optimize_acqf_and_get_observation(EI, objective_function, time_list, global_start_time)
        # update training points
        train_x = torch.cat([train_x, new_x])
        train_obj = torch.cat([train_obj, new_obj])
        # reinitialize the models so they are ready for fitting on next iteration
        # use the current state dict to speed up fitting
        if refit == 1:
            mll, model = initialize_model(train_x, train_obj)
        else:
            mll, model = initialize_model(
                train_x,
                train_obj,
                model.state_dict(),
            )
        t1 = time.time()
        print("Iter %d: x=%s, perf=%s, time=%.2f, global_time=%.2f"
              % (iteration, unnormalize(new_x, bounds=problem_bounds), -new_obj, t1-t0, time_list[-1]), flush=True)

    # Save result
    X = unnormalize(train_x, bounds=problem_bounds).cpu().numpy().astype(np.float64)  # caution
    perf_list = (-1 * train_obj.reshape(-1).cpu().numpy().astype(np.float64)).tolist()
    return X, perf_list, time_list


with timeit('%s all' % (mth,)):
    for run_i in range(start_id, start_id + rep):
        seed = seeds[run_i]
        with timeit('%s %d %d' % (mth, run_i, seed)):
            # Evaluate
            X, perf_list, time_list = evaluate(mth, run_i, seed)

            # Save result
            print('=' * 20)
            print(seed, mth, X, perf_list, time_list)
            print(seed, mth, 'best perf', np.min(perf_list))

            timestamp = time.strftime('%Y-%m-%d-%H-%M-%S', time.localtime(time.time()))
            dir_path = 'logs/so_benchmark_%s_%d/%s/' % (problem_str, max_runs, mth)
            file = 'benchmark_%s_%04d_%s.pkl' % (mth, seed, timestamp)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            with open(os.path.join(dir_path, file), 'wb') as f:
                save_item = (X, perf_list, time_list)
                pkl.dump(save_item, f)
            print(dir_path, file, 'saved!', flush=True)
