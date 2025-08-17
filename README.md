# BeatBank

**BeatBank** is a blockchain-backed audio service that allows users to upload audio files, pay via [x402.org](https://x402.org) open payment protocol, and receive separated stems (vocals, drums, bass, etc.) for download.

The project leverages **Hedera Consensus Service** to manage workflow transparency and auditability. Each audio processing request is recorded as a message on Hedera, and when stem separation is complete, another message confirms that the processed files have been uploaded to **Walrus** for secure retrieval.

---

## ✨ Features
- Upload audio tracks and separate them into stems (vocals, drums, bass, etc.)
- Payments handled through **x402.org Open Payment Protocol**
- Workflow events logged to **Hedera Consensus Service** for transparency
- Output stems stored on **Walrus** distributed storage
- Verifiable, decentralized, and user-friendly

---

## 🚀 How It Works
1. User uploads an audio file via the frontend.
2. Payment is handled through x402.org protocol.
3. A request message is posted to Hedera, ensuring auditability and consensus.
4. BeatBank processes the audio into stems using machine learning models.
5. The resulting files are uploaded to Walrus.
6. A completion message is posted on Hedera with a reference to the output location.
7. User retrieves the processed stems.

---

# Prerequisites

Before running the BeatBank + x402 prototype, make sure the following are in place:

## 1. Python Environment
- **Python 3.11+** installed (tested with 3.11).
- A virtual environment created and activated:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

## 2. Dependencies
- Install required Python packages:
  ```bash
  pip install -r requirements.txt
  ```
  Includes FastAPI, httpx, colorama, dotenv, Hedera SDK.

## 3. Hedera Testnet Account
- Obtain from [Hedera Portal](https://portal.hedera.com/).
- Save in `.env`:
  ```env
  HEDERA_OPERATOR_ID=0.0.xxxxx
  HEDERA_OPERATOR_KEY=302e0201...   # Hedera private key
  HEDERA_TOPIC_ID=0.0.yyyyy         # Topic for job messages
  ```

## 4. x402 Test Account
- Generate Ethereum-compatible key.
- Save in `.env`:
  ```env
  PRIVATE_KEY=0xabc123...
  ```

## 5. Test Audio File
- Place in project root or `.env`:
  ```env
  TEST_FILE=demo.mp3
  ```

## 6. Running the Server
```bash
./run.sh
```

## 7. Running the Client
```bash
python client_payer.py
```

---

![Flow Diagram](beatbank_x402_flow.png)
## 🛠️ Technologies
*(Details coming soon – this section will be updated as the stack is finalized)*

---

## 📜 Roadmap
- [ ] Initial prototype with x402.org + Hedera integration
- [ ] Audio processing pipeline with stem separation
- [ ] Walrus integration for distributed storage
- [ ] Frontend for uploads and downloads
- [ ] Testnet deployment
- [ ] Mainnet launch

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome!  
Feel free to open a pull request or file an issue.

---

## 📄 License
This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

