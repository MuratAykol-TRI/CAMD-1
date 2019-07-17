#  Copyright (c) 2019 Toyota Research Institute.  All rights reserved.

import unittest
import boto3
import json
import time
from camd import CAMD_S3_BUCKET
from camd.campaigns.worker import Worker

def teardown_s3():
    """Tear down test files in s3"""
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(CAMD_S3_BUCKET)
    bucket.objects.filter(Prefix="{}".format("test")).delete()


class WorkerTest(unittest.TestCase):
    def tearDown(self):
        teardown_s3()

    def submit_chemsyses(self, chemsyses):
        # Upload three things to s3
        s3_resource = boto3.resource("s3")
        for chemsys in chemsyses:
            key = "test/submit/{}/status.json".format(chemsys)
            obj = s3_resource.Object(CAMD_S3_BUCKET, key)
            obj.put(Body=json.dumps({"last_submitted": 10}))
            time.sleep(1)

    def put_runs(self, chemsyses):
        # Upload three things to s3
        s3_resource = boto3.resource("s3")
        for chemsys in chemsyses:
            key = "test/runs/{}/job_status.json".format(chemsys)
            obj = s3_resource.Object(CAMD_S3_BUCKET, key)
            obj.put(Body=json.dumps({"status": "started"}))

            key = "test/runs/{}/job_status.json".format(chemsys)
            obj = s3_resource.Object(CAMD_S3_BUCKET, key)
            obj.put(Body=json.dumps({"status": "started"}))


    def test_get_latest_chemsys(self):
        self.submit_chemsyses(["O-V", "O-Ti", "Fe-O"])
        worker = Worker("random_atf", s3_prefix="test")
        latest_chemsys = worker.get_latest_chemsys()
        self.assertEqual(latest_chemsys, "Fe-O")

        self.put_runs(["Fe-O"])
        latest_chemsys = worker.get_latest_chemsys()
        self.assertEqual(latest_chemsys, "O-Ti")

        self.put_runs(["O-V", "O-Ti"])
        latest_chemsys = worker.get_latest_chemsys()
        self.assertIsNone(latest_chemsys)


    def test_run_atf_campaign(self):
        self.submit_chemsyses(["O-Ti", "Fe-O"])
        worker = Worker("random_atf", s3_prefix="test")

        latest_chemsys = worker.get_latest_chemsys()
        self.assertEqual(latest_chemsys, "Fe-O")

        worker.start(num_loops=1)
        latest_chemsys = worker.get_latest_chemsys()
        self.assertEqual(latest_chemsys, "O-Ti")

        worker.start(num_loops=1)
        latest_chemsys = worker.get_latest_chemsys()
        self.assertIsNone(latest_chemsys)


if __name__ == '__main__':
    unittest.main()
