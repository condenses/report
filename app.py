from fastapi import FastAPI, Request, Depends, HTTPException
import pymongo
import os
import bittensor as bt
from dependencies import check_authentication
import threading
import time
from pydantic import BaseModel


class ReportBatch(BaseModel):
    comparision: dict
    challenge: dict
    task: str
    tier: str


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

        # Start background tasks in separate threads
        threading.Thread(
            target=self.clean_old_batch_reports_periodically, daemon=True
        ).start()

        # FastAPI app initialization
        self.app = FastAPI()

        @self.app.post("/api/report-metadata")
        def report_metadata(item: dict, request: Request):
            # Pass metagraph and min_stake to check_authentication
            ss58_address, uid = check_authentication(
                request, self.metagraph, self.MIN_STAKE
            )
            validator_collection = self.DB["metadata"]
            current_time = time.time()
            validator_collection.update_one(
                {"_id": ss58_address},
                {
                    "$set": {
                        "hotkey": ss58_address,
                        "uid":uid
                    },
                    "$push": {
                        "reports": {
                            "$each": [
                                {
                                    "metadata": item,     
                                    "timestamp": current_time
                                }
                            ],
                            "$sort": {"timestamp": -1},
                            "$slice": 10                
                        }
                    }
                },
                upsert=True
            )

            return {"message": "Item uploaded successfully"}

        @self.app.post("/api/report-batch")
        def report_batch(item: ReportBatch, request: Request):
            ss58_address, uid = check_authentication(
                request, self.metagraph, self.MIN_STAKE
            )
            validator_collection = self.DB["batch-reports"]
            timestamp = time.time()
            result = validator_collection.insert_one(
                {
                    "_id": f"{ss58_address}-{timestamp}",
                    "batch_report": item.comparision,
                    "task": item.task,
                    "tier": item.tier,
                    "timestamp": timestamp,
                    "uid": uid,
                }
            )
            print(result)

            validator_collection = self.DB["batch-challenges"]
            result = validator_collection.insert_one(
                {
                    "_id": f"{ss58_address}-{timestamp}",
                    "challenge": item.challenge,
                    "task": item.task,
                    "tier": item.tier,
                    "timestamp": timestamp,
                    "uid": uid,
                }
            )
            print(result)
            return {"message": "Item uploaded successfully"}

        @self.app.get("/api/get-metadata")
        def get_metadata():
            validator_collection = self.DB["metadata"]
            metadata = list(validator_collection.find())
            return {"metadata": metadata}

        @self.app.get("/api/get-batch-reports/{last_n_minutes}")
        def get_batch_reports(last_n_minutes: int):
            validator_collection = self.DB["batch-reports"]
            batch_reports = list(
                validator_collection.find(
                    {"timestamp": {"$gt": time.time() - last_n_minutes * 60}}
                )
            )
            return {"batch_reports": batch_reports}
        
        @self.app.get("/get_coldkey_report/{coldkey}")
        def get_coldkey_report(coldkey: str):
            coldkey_uid_map = dict(zip(self.metagraph.uids.tolist(), self.metagraph.coldkeys))
            uids = [uid for uid, ck in coldkey_uid_map.items() if ck == coldkey]
            return {"uids": uids}


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

    def clean_old_batch_reports_periodically(self):
        """
        Periodically clean batch reports older than 6 hours.
        """
        while True:
            try:
                print("Cleaning old batch reports")
                validator_collection = self.DB["batch-reports"]
                validator_collection.delete_many(
                    {"timestamp": {"$lt": time.time() - 21600}}
                )
                print("Old batch reports cleaned")
            except Exception as e:
                print(f"Error during cleaning batch reports: {e}")
            time.sleep(3600)  # Clean every hour


vrg = ValidatorReportGather()
app = vrg.app

if __name__ == "__main__":
    # Start the FastAPI app
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
