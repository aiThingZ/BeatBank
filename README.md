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

