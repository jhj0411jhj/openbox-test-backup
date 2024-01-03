# License: MIT
import numpy as np
import matplotlib.pyplot as plt
from openbox import Advisor, space as sp, Observation, logger
from openbox.utils.constants import SUCCESS


# Define Objective Function
def branin(config):
    x1, x2 = config['x1'], config['x2']
    y = (x2 - 5.1 / (4 * np.pi ** 2) * x1 ** 2 + 5 / np.pi * x1 - 6) ** 2 \
        + 10 * (1 - 1 / (8 * np.pi)) * np.cos(x1) + 10
    return {'objectives': [y]}


def test_examples_ask_and_tell_interface():
    # Define Search Space
    space = sp.Space()
    x1 = sp.Real("x1", -5, 10, default_value=0)
    x2 = sp.Real("x2", 0, 15, default_value=0)
    space.add_variables([x1, x2])

    # Run
    advisor = Advisor(
        space,
        # surrogate_type='gp',
        surrogate_type='auto',
        task_id='ask_and_tell',
        output_dir='logs/pytest/',
    )

    MAX_RUNS = 20
    for i in range(MAX_RUNS):
        # ask
        config = advisor.get_suggestion()
        # evaluate
        ret = branin(config)
        # tell
        observation = Observation(config=config, objectives=ret['objectives'])
        advisor.update_observation(observation)
        logger.info('\n===== ITER %d/%d: %s.' % (i+1, MAX_RUNS, observation))

    history = advisor.get_history()
    print(history)

    history.plot_convergence(true_minimum=0.397887)
    # plt.show()
    plt.savefig('logs/pytest/ask_and_tell_convergence.png')
    plt.close()

    # install pyrfr to use get_importance()
    print(history.get_importance())

    # Have a try on the new HTML visualization feature!
    # You can also call visualize_html() after optimization.
    # For 'show_importance' and 'verify_surrogate', run 'pip install "openbox[extra]"' first
    history.visualize_html(open_html=False, show_importance=True, verify_surrogate=True, advisor=advisor,
                           logging_dir='logs/pytest/')

    assert history.trial_states.count(SUCCESS) == MAX_RUNS
