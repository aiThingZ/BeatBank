import os
from dotenv import load_dotenv
from hedera import (
    Client,
    AccountId,
    PrivateKey,
    TopicMessageSubmitTransaction,
    TopicId
)

load_dotenv()

# Get values from .env
OPERATOR_ID = AccountId.fromString(os.environ["HEDERA_OPERATOR_ID"])
OPERATOR_KEY = PrivateKey.fromString(os.environ["HEDERA_OPERATOR_KEY"])
TOPIC_ID = TopicId.fromString(os.environ["HEDERA_TOPIC_ID"])

# Use correct Java-style camelCase
client = Client.forTestnet()
client.setOperator(OPERATOR_ID, OPERATOR_KEY)

# Build and send message
message = "Hello from BeatBank 🚀"
tx = TopicMessageSubmitTransaction().setTopicId(TOPIC_ID).setMessage(message)
resp = tx.execute(client)
receipt = resp.getReceipt(client)

print("Message submitted. Status:", receipt.status.toString())

