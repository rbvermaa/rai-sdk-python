import json
from time import sleep
import unittest
import os
import uuid
import tempfile

from pathlib import Path
from railib import api, config

# TODO: create_engine_wait should be added to API
# with exponential backoff


def create_engine_wait(ctx: api.Context, engine: str):
    state = api.create_engine(ctx, engine, headers=custom_headers)["compute"]["state"]

    count = 0
    while not ("PROVISIONED" == state):
        if count > 12:
            return

        count += 1
        sleep(30)
        state = api.get_engine(ctx, engine)["state"]


# Get creds from env vars if exists
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
client_credentials_url = os.getenv("CLIENT_CREDENTIALS_URL")
custom_headers = json.loads(os.getenv('CUSTOM_HEADERS', '{}'))

if client_id is None:
    print("using config from path")
    cfg = config.read()
else:
    file = tempfile.NamedTemporaryFile(mode="w")
    file.writelines(f"""
    [default]
    client_id={client_id}
    client_secret={client_secret}
    client_credentials_url={client_credentials_url}
    region=us-east
    port=443
    host=azure.relationalai.com
    """)
    file.seek(0)
    cfg = config.read(fname=file.name)
    file.close()

ctx = api.Context(**cfg)

suffix = uuid.uuid4()
engine = f"python-sdk-{suffix}"
dbname = f"python-sdk-{suffix}"


class TestTransactionAsync(unittest.TestCase):
    def setUp(self):
        create_engine_wait(ctx, engine)
        api.create_database(ctx, dbname)

    def test_v2_exec(self):
        cmd = "x, x^2, x^3, x^4 from x in {1; 2; 3; 4; 5}"
        rsp = api.exec(ctx, dbname, engine, cmd)

        # transaction
        self.assertEqual("COMPLETED", rsp.transaction["state"])

        # metadata
        with open(os.path.join(Path(__file__).parent, "metadata.pb"), "rb") as f:
            data = f.read()
            self.assertEqual(
                rsp.metadata,
                api._parse_metadata_proto(data)
            )

        # problems
        self.assertEqual(0, len(rsp.problems))

        # results
        self.assertEqual(
            {
                'v1': [
                    1, 2, 3, 4, 5], 'v2': [
                    1, 4, 9, 16, 25], 'v3': [
                    1, 8, 27, 64, 125], 'v4': [
                        1, 16, 81, 256, 625]}, rsp.results[0]["table"].to_pydict())

    def tearDown(self):
        api.delete_engine(ctx, engine)
        api.delete_database(ctx, dbname)


if __name__ == '__main__':
    unittest.main()
