from fastapi import FastAPI, Request, Depends, HTTPException
import pymongo
import os
import bittensor as bt
from dependencies import check_authentication
import threading
import time


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
        self.NETUID = os.getenv("NETUID", 52)
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
