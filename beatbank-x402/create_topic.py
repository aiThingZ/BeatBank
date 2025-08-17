# create_topic.py
import os
from dotenv import load_dotenv
from hedera import Client, AccountId, PrivateKey, TopicCreateTransaction

load_dotenv()

network = os.getenv("HEDERA_NETWORK", "testnet").lower()
op_id = AccountId.fromString(os.environ["HEDERA_OPERATOR_ID"])
op_key = PrivateKey.fromString(os.environ["HEDERA_OPERATOR_KEY"])

# Use Java-style method names
if network == "testnet":
    client = Client.forTestnet()
elif network == "previewnet":
    client = Client.forPreviewnet()
else:
    client = Client.forMainnet()

client.setOperator(op_id, op_key)

tx = TopicCreateTransaction().setTopicMemo("BeatBank Events").freezeWith(client)
tx = tx.sign(op_key)  # optional if operator is set
resp = tx.execute(client)
receipt = resp.getReceipt(client)

topic_id = receipt.topicId
print(f"HEDERA_TOPIC_ID={topic_id.toString()}")


