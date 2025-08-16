# create_topic.py
import os
from dotenv import load_dotenv
from hedera import Client, AccountId, PrivateKey, TopicCreateTransaction

load_dotenv()

network = os.getenv("HEDERA_NETWORK", "testnet").lower()
op_id = AccountId.fromString(os.environ["HEDERA_OPERATOR_ID"])
op_key = PrivateKey.fromString(os.environ["HEDERA_OPERATOR_KEY"])

if network == "testnet":
    client = Client.for_testnet()
elif network == "previewnet":
    client = Client.for_previewnet()
else:
    client = Client.for_mainnet()

client.set_operator(op_id, op_key)

tx = TopicCreateTransaction().setTopicMemo("BeatBank Events").freezeWith(client)
tx = tx.sign(op_key)  # optional with operator set, but fine
resp = tx.execute(client)
receipt = resp.getReceipt(client)

topic_id = receipt.topicId
print("HEDERA_TOPIC_ID:", topic_id)

