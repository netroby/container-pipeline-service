#!/usr/bin/env python

import json
import logging
import os

from container_pipeline.lib.log import load_logger
from container_pipeline.workers.base import BaseWorker
from container_pipeline.lib import settings
from container_pipeline.lib.command import run_cmd


class DockerfileLintWorker(BaseWorker):
    """
    Dockerfile lint worker lints the Dockerfile using the projectatomic's
    dockerfile_lint tool. https://github.com/projectatomic/dockerfile_lint
    """
    NAME = 'Linter worker'

    def handle_job(self, job):
        """
        This menthod handles the job received for dockerfile lint worker.
        """
        self.logger.info("Received job for Dockerfile lint: %s" % job)
        self.logger.debug("Writing Dockerfile to /tmp/scan/Dockerfile")
        self.write_dockerfile(job.get("dockerfile"))
        self.logger.debug("Running Dockerfile Lint check")
        self.lint(job)

    def write_dockerfile(self, dockerfile):
        """
        Write dockerfile at temporary location to run lint upon
        """
        if os.path.isdir("/tmp/scan"):
            self.logger.debug("/tmp/scan directory already exists")
        elif os.path.isfile("/tmp/scan"):
            os.remove("/tmp/scan")
            os.makedirs("/tmp/scan")
        else:
            os.makedirs("/tmp/scan")

        with open("/tmp/scan/Dockerfile", "w") as f:
            f.write(dockerfile)

    def lint(self, job):
        """
        Lint the Dockerfile received
        """
        command = ("docker run --rm -v /tmp/scan:/root/scan:Z "
                   "registry.centos.org/pipeline-images/dockerfile-lint")
        try:
            out = run_cmd(command)
        except Exception as e:
            self.logger.warning(
                "Dockerfile Lint check failed", extra={'locals': locals()})
            response = {
                "linter_results": False,
                "action": "notify_user",
                "namespace": job.get('namespace'),
                "notify_email": job.get("notify_email"),
                "job_name": job.get("job_name"),
                "msg": str(e),
            }
        else:
            self.logger.info("Dockerfile Lint check done. Exporting logs.")
            # logs file for linter
            linter_results_path = os.path.join(
                job.get("logs_dir"),
                settings.LINTER_RESULT_FILE
            )

            # logs URL for linter results
            logs_URL = linter_results_path.replace(
                settings.LOGS_DIR_BASE,   # /srv/pipeline-logs/
                settings.LOGS_URL_BASE   # https://registry.centos.org
            )

            out += "\nHosted linter results : %s\n" % logs_URL
            # export linter results
            self.export_logs(out, linter_results_path)

            response = {
                "logs": out,
                "linter_results": True,
                "action": "notify_user",
                "namespace": job.get('namespace'),
                "notify_email": job.get("notify_email"),
                "job_name": job.get("job_name"),
                "msg": None,
                "linter_results_path": linter_results_path,
                "logs_URL": logs_URL,
            }

        # linter execution status file path
        status_file_path = os.path.join(
            job.get("logs_dir"),
            settings.LINTER_STATUS_FILE
        )
        # now export the status about linter execution in logs dir of the job
        # this response will be read after job builds and while sending
        # email to user. Details from this response is used to generate email.

        # TODO: Write export JSON method in base worker
        self.export_linter_status(response, status_file_path)

    def export_linter_status(self, status, status_file_path):
        """
        Export status of linter execution for build in process
        """
        try:
            with open(status_file_path, "w") as fin:
                json.dump(status, fin)
        except IOError as e:
            self.logger.error(
                "Failed to write linter status on NFS share: {}".format(e))
        else:
            self.logger.debug(
                    "Wrote linter status to file: %s" % status_file_path)


if __name__ == '__main__':
    load_logger()
    logger = logging.getLogger('dockerfile-linter')
    worker = DockerfileLintWorker(
        logger, sub='start_linter', pub='master_tube')
    worker.run()