
from fastapi import FastAPI, Request, Depends
from dependencies import check_authentication
import pymongo
import os


class ProxyApp:
    def __init__(self):
        """
        Initialize the ValidatorApp with necessary configurations, database connections, and background tasks.
        """
        print("Initializing ValidatorApp")

        self.MONGOHOST = os.getenv("MONGOHOST", "localhost")
        self.MONGOPORT = int(os.getenv("MONGOPORT", 27017))
        self.MONGOUSER = os.getenv("MONGOUSER", "root")
        self.MONGOPASSWORD = os.getenv("MONGOPASSWORD", "example")


        try:
            self.client = pymongo.MongoClient(
                f"mongodb://{self.MONGOUSER}:{self.MONGOPASSWORD}@{self.MONGOHOST}:{self.MONGOPORT}"
            )
            self.DB = self.client["ncs-client"]
            print(f"Connected to MongoDB at {self.MONGOHOST}:{self.MONGOPORT}")
        except Exception as e:
            print(f"Failed to connect to MongoDB: {e}")
            raise



        self.in_memory_validators = {}
        self.validators = []
        self.app = FastAPI()

        @self.app.post("/store_miner_info")
        async def store_miner_info(item: dict,request: Request):
            check_authentication(request)
            validator_collection = self.DB["validator_info"]
            uid = item["uid"]
            print(uid, item.get("version", "no-version"))
            validator_collection.update_one(
                {"_id": uid},
                {"$set": item},
                upsert=True
            )

            return {"message": "Item uploaded successfully"}

        @self.app.get("/get_miner_info")
        async def get_miner_info():
            validator_info = {}
            validator_collection = self.DB["validator_info"]
            for validator in validator_collection.find():
                try:
                    uid = validator['uid']

                    validator_info[uid] = {
                        "info": validator["info"],
                    }
                except Exception as e:
                    print(e)
                    print(str(validator)[:100])
                    continue
            return validator_info     

validator_app = ProxyApp()
app = validator_app.app

if __name__ == "__main__":
    # Start the FastAPI app
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=10931)
