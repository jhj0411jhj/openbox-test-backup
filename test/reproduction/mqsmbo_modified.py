import time
from openbox import logger
from openbox.optimizer.message_queue_smbo import mqSMBO
from openbox.utils.history import Observation


class mqSMBO_modified(mqSMBO):
    """
    record config_list, perf_list, time_list.
    run with time limit.
    single objective only.
    """

    def async_run_with_limit(self, max_runtime):
        config_num = 0
        result_num = 0
        while result_num < self.max_runs:
            # Add jobs to masterQueue.
            while len(self.config_advisor.running_configs) < self.batch_size and config_num < self.max_runs:
                config_num += 1
                config = self.config_advisor.get_suggestion()
                msg = [config, self.max_runtime_per_trial]
                logger.info("Master: Add config %d." % config_num)
                self.master_messager.send_message(msg)

            # Get results from workerQueue.
            while True:
                observation = self.master_messager.receive_message()
                if observation is None:
                    # Wait for workers.
                    # logger.info("Master: wait for worker results. sleep 1s.")
                    time.sleep(self.sleep_time)
                    break
                # Report result.
                result_num += 1
                if observation.objectives is None:
                    observation.objectives = self.FAILED_PERF.copy()
                self.config_advisor.update_observation(observation)
                logger.info('Master: Get %d observation: %s' % (result_num, str(observation)))

                global_time = time.time() - self.global_start_time
                self.config_list.append(observation.config)
                self.perf_list.append(observation.objectives[0])  # single objective
                self.time_list.append(global_time)

            global_time = time.time() - self.global_start_time
            if global_time >= max_runtime:
                return

    def sync_run_with_limit(self, max_runtime):
        batch_num = (self.max_runs + self.batch_size - 1) // self.batch_size
        if self.batch_size > self.config_advisor.init_num:
            batch_num += 1  # fix bug
        batch_id = 0
        while batch_id < batch_num:
            configs = self.config_advisor.get_suggestions()
            # Add batch configs to masterQueue.
            for config in configs:
                msg = [config, self.max_runtime_per_trial]
                self.master_messager.send_message(msg)
            logger.info('Master: %d-th batch. %d configs sent.' % (batch_id, len(configs)))
            # Get batch results from workerQueue.
            result_num = 0
            result_needed = len(configs)
            while True:
                observation = self.master_messager.receive_message()
                if observation is None:
                    # Wait for workers.
                    # logger.info("Master: wait for worker results. sleep 1s.")
                    time.sleep(self.sleep_time)
                    continue
                # Report result.
                result_num += 1
                if observation.objectives is None:
                    observation.objectives = self.FAILED_PERF.copy()
                self.config_advisor.update_observation(observation)
                logger.info('Master: In the %d-th batch [%d], observation is: %s'
                                 % (batch_id, result_num, str(observation)))

                global_time = time.time() - self.global_start_time
                self.config_list.append(observation.config)
                self.perf_list.append(observation.objectives[0])  # single objective
                self.time_list.append(global_time)

                if result_num == result_needed:
                    break
            batch_id += 1

            global_time = time.time() - self.global_start_time
            if global_time >= max_runtime:
                return

    def run_with_limit(self, max_runtime):
        self.max_runs = max(self.max_runs, 10000)
        self.sleep_time = 0.1
        self.global_start_time = time.time()
        self.config_list = []
        self.perf_list = []
        self.time_list = []
        if self.parallel_strategy == 'async':
            self.async_run_with_limit(max_runtime)
        else:
            self.sync_run_with_limit(max_runtime)
