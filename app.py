from fastapi import FastAPI, Request, Depends, HTTPException
import pymongo
import os
import bittensor as bt
from dependencies import check_authentication
import threading
import time
import wandb
from starlette.requests import Request
from starlette.datastructures import Headers
from fastapi import HTTPException

class ValidatorReportGather:
    def __init__(self):
        """
        Initialize the ProxyApp with necessary configurations, database connections, and background tasks.
        """
        print("Initializing ProxyApp")

        # Environment variables
        self.MONGOHOST = os.getenv("MONGOHOST", "localhost")
        self.MONGOPORT = int(os.getenv("MONGOPORT", 27017))
        self.MONGOUSER = os.getenv("MONGOUSER", "root")
        self.MONGOPASSWORD = os.getenv("MONGOPASSWORD", "example")
        self.SUBTENSOR_NETWORK = os.getenv("SUBTENSOR_NETWORK", "finney")
        self.NETUID = os.getenv("NETUID", 47)
        self.MIN_STAKE = int(os.getenv("MIN_STAKE", 10000))
        self.WANDB_API_KEY=os.getenv("WANDB_API_KEY","")
        self.wandb_api = wandb.Api()

        # Initialize synchronous MongoDB connection
        try:
            self.client = pymongo.MongoClient(
                f"mongodb://{self.MONGOUSER}:{self.MONGOPASSWORD}@{self.MONGOHOST}:{self.MONGOPORT}"
            )
            self.DB = self.client["subnet-metrics"]
            print(f"Connected to MongoDB at {self.MONGOHOST}:{self.MONGOPORT}")
        except Exception as e:
            print(f"Failed to connect to MongoDB: {e}")
            raise

        # Initialize Subtensor
        try:
            self.subtensor = bt.subtensor(network=self.SUBTENSOR_NETWORK)
            self.metagraph = self.subtensor.metagraph(self.NETUID)
            print(f"Connected to Subtensor network {self.SUBTENSOR_NETWORK}")
        except Exception as e:
            print(f"Failed to initialize Subtensor: {e}")
            raise

        # Start resync_metagraph_periodically in a separate thread
        threading.Thread(target=self.resync_metagraph_periodically, daemon=True).start()

        # FastAPI app initialization
        self.app = FastAPI()

        @self.app.post("/api/report")
        def report(item: dict, request: Request):
            # Pass metagraph and min_stake to check_authentication
            ss58_address, uid = check_authentication(
                request, self.metagraph, self.MIN_STAKE
            )
            validator_collection = self.DB["validator-reports"]
            validator_collection.update_one(
                {"_id": ss58_address},
                {"$set": {"report": item, "uid": uid, "hotkey": ss58_address}},
                upsert=True,
            )

            return {"message": "Item uploaded successfully"}

        @self.app.get("/api/get-reports")
        def get_report():
            validator_collection = self.DB["validator-reports"]
            reports = list(validator_collection.find())
            return {"reports": reports}
        
        @self.app.get("/api/get-wandb/{ss58_address}")
        def get_wandb(ss58_address: str):
            runs = self.wandb_api.runs('toilaluan/Neural-Condense-Subnet', per_page=1000, order="-created_at")
            validator_info = {}
            for run in runs:
                if run.state == "running":
                    data = run.history()
                    data['_runtime']=round(data['_runtime'])
                    max_runtime_data = data[data['_runtime'] == data['_runtime'].max()]

                    config = {k: v for k, v in run.config.items() if not k.startswith('_')}
                    if ss58_address == config.get('ss58_address'):
                        fake_headers = Headers({
                            "ss58_address": config['ss58_address'],
                            "signature": config['signature'],
                            "message": config['message'],
                        })
                        fake_request = Request(scope={"type": "http", "headers": fake_headers.raw})
                        
                        # Validate and authenticate
                        ss58_address, uid = check_authentication(fake_request, self.metagraph, self.MIN_STAKE)
                        
                        # Filter data based on conditions
                        max_runtime_data_filtered = max_runtime_data.drop(columns=['_runtime', '_step', '_timestamp'], errors='ignore')

                        filtered_dict = {
                            col: max_runtime_data_filtered[col].dropna().iloc[0]
                            for col in max_runtime_data_filtered.columns
                            if max_runtime_data_filtered[col].notna().any() and (max_runtime_data_filtered[col] > 0).any()
                        }

                        # Format the filtered data
                        formatted_data = {}
                        for key, value in filtered_dict.items():
                            tier_id, metric = key.split('/')
                            tier, id_ = tier_id.split('-')
                            if id_ not in formatted_data:
                                formatted_data[id_] = {"tier": tier, "loss": 0}              
                            if metric == 'penalized_scores':
                                formatted_data[id_]["score"] = value
                            elif metric == 'losses':
                                formatted_data[id_]["loss"] = value

                        validator_info={
                            'name':run.name,
                            'report':{'metadata:':formatted_data},
                            'hotkey':config['ss58_address'],
                            'uid':config['uid'],
                        }

            return validator_info


    def resync_metagraph_periodically(self):
        """
        Periodically resync the Subtensor metagraph to keep it updated.
        """
        while True:
            try:
                print("Resyncing metagraph")
                self.metagraph.sync()
                print("Metagraph resynced")
            except Exception as e:
                print(f"Error during metagraph resync: {e}")
            time.sleep(600)  # Resync every 15 minutes


vrg = ValidatorReportGather()
app = vrg.app

if __name__ == "__main__":
    # Start the FastAPI app
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
