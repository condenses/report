from fastapi import Request
from fastapi.exceptions import HTTPException
import bittensor as bt


def check_authentication(request: Request, metagraph, min_stake: int = 10000):
    message = request.headers.get("message")
    ss58_address = request.headers.get("ss58_address")
    signature = request.headers.get("signature")
    keypair = bt.Keypair(ss58_address=ss58_address)
    print(f"Checking authentication for {ss58_address}")
    if not keypair.verify(message, signature):
        raise HTTPException(status_code=401, detail="Invalid token")
    if ss58_address not in metagraph.hotkeys:
        raise HTTPException(
            status_code=401, detail="Validator not registered on subnet"
        )
    uid = metagraph.hotkeys.index(ss58_address)
    stake = metagraph.total_stake[uid]
    print(f"Stake: {stake}, SS58: {ss58_address}")
    if stake < min_stake:
        raise HTTPException(status_code=401, detail="Stake below minimum")
    print(f"Authenticated {ss58_address}")
    return ss58_address, uid