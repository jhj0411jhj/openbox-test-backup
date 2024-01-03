"""
example cmdline:

python test/reproduction/so/benchmark_so_random_math.py --problem branin --times 1 --n 200 --rep 1 --start_id 0

"""
import os
import sys
import time
import numpy as np
import argparse
import pickle as pkl

sys.path.insert(0, os.getcwd())
from test.reproduction.so.so_benchmark_function import get_problem
from openbox.optimizer.generic_smbo import SMBO
from test.reproduction.test_utils import timeit, seeds

parser = argparse.ArgumentParser()
parser.add_argument('--problem', type=str)
parser.add_argument('--times', type=int, default=1)
parser.add_argument('--n', type=int, default=100)
parser.add_argument('--rep', type=int, default=1)
parser.add_argument('--start_id', type=int, default=0)

args = parser.parse_args()
problem_str = args.problem
times = args.times
max_runs = args.n * times
rep = args.rep
start_id = args.start_id
mth = 'random-n%d' % (times,)

problem = get_problem(problem_str)
cs = problem.get_configspace(optimizer='smac')
max_runtime_per_trial = 600
task_id = '%s_%s' % (mth, problem_str)


def evaluate(mth, run_i, seed):
    print(mth, run_i, seed, '===== start =====', flush=True)

    def objective_function(config):
        y = problem.evaluate_config(config)
        res = dict()
        res['config'] = config
        res['objectives'] = (y,)
        res['constraints'] = None
        return res

    bo = SMBO(objective_function, cs,
              sample_strategy='random',
              init_strategy='random',
              max_runs=max_runs,
              max_runtime_per_trial=max_runtime_per_trial, task_id=task_id, random_state=seed)
    # bo.run()
    config_list = []
    perf_list = []
    time_list = []
    global_start_time = time.time()
    for i in range(max_runs):
        config, trial_state, objectives, trial_info = bo.iterate()
        global_time = time.time() - global_start_time
        print(seed, i, objectives, config, trial_state, trial_info, 'time=', global_time)
        config_list.append(config)
        perf_list.append(objectives[0])
        time_list.append(global_time)

    return config_list, perf_list, time_list


with timeit('%s all' % (mth,)):
    for run_i in range(start_id, start_id + rep):
        seed = seeds[run_i]
        with timeit('%s %d %d' % (mth, run_i, seed)):
            # Evaluate
            config_list, perf_list, time_list = evaluate(mth, run_i, seed)

            # Save result
            print('=' * 20)
            print(seed, mth, config_list, perf_list, time_list)
            print(seed, mth, 'best perf', np.min(perf_list))

            timestamp = time.strftime('%Y-%m-%d-%H-%M-%S', time.localtime(time.time()))
            dir_path = 'logs/so_benchmark_%s_%d/%s/' % (problem_str, max_runs/times, mth)
            file = 'benchmark_%s_%04d_%s.pkl' % (mth, seed, timestamp)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            with open(os.path.join(dir_path, file), 'wb') as f:
                save_item = (config_list, perf_list, time_list)
                pkl.dump(save_item, f)
            print(dir_path, file, 'saved!', flush=True)
