from fastapi import FastAPI, Request, Depends, HTTPException
import motor.motor_asyncio
import os
import bittensor as bt
import asyncio
from dependencies import check_authentication


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

        # Initialize async MongoDB connection
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
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

        # Periodic metagraph resync
        asyncio.create_task(self.resync_metagraph_periodically())

        # FastAPI app initialization
        self.app = FastAPI()

        @self.app.post("/api/report")
        async def report(item: dict, request: Request):
            # Pass metagraph and min_stake to check_authentication
            ss58_address, uid = await check_authentication(
                request, self.metagraph, self.MIN_STAKE
            )
            validator_collection = self.DB["validator-reports"]
            await validator_collection.update_one(
                {"_id": ss58_address},
                {"$set": {"report": item, "uid": uid, "hotkey": ss58_address}},
                upsert=True,
            )

            return {"message": "Item uploaded successfully"}

        @self.app.get("/api/get-reports")
        async def get_report():
            validator_collection = self.DB["validator-reports"]
            reports = await validator_collection.find().to_list(length=None)
            return {"reports": reports}

    async def resync_metagraph_periodically(self):
        """
        Periodically resync the Subtensor metagraph to keep it updated.
        """
        while True:
            try:
                print("Resyncing metagraph")
                await asyncio.to_thread(self.metagraph.sync)
                print("Metagraph resynced")
            except Exception as e:
                print(f"Error during metagraph resync: {e}")
            await asyncio.sleep(600)  # Resync every 15 minutes


vrg = ValidatorReportGather()
app = vrg.app
