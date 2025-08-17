#!/usr/bin/env node
/**
 * Walrus uploader (Node + TypeScript SDK, runnable as plain Node)
 *
 * Uploads one or more files as a single Walrus Quilt and prints a JSON
 * result to stdout:
 *   {
 *     "ok": true,
 *     "network": "testnet",
 *     "quiltId": "<ID>",
 *     "blobId": "<ID>",
 *     "files": [
 *        {"path": "...", "identifier": "vocals.wav"},
 *        {"path": "...", "identifier": "vocals_cleaned.wav"}
 *     ]
 *   }
 *
 * ENV you must set:
 *   WALRUS_NETWORK=testnet|mainnet (default: testnet)
 *   SUI_FULLNODE_URL= (optional; default uses SDK getFullnodeUrl)
 *   SUI_MNEMONIC= "..."  // or SUI_PRIVATE_KEY= "0x..."
 *   WALRUS_EPOCHS=3      // how long to store
 *   WALRUS_DELETABLE=1   // optional; default 1 (true)
 *
 * Optional Upload Relay (recommended):
 *   UPLOAD_RELAY_HOST=https://upload-relay.testnet.walrus.space
 *   RELAY_TIP_MAX=1000   // in MIST (SUI's unit). See docs for tip-config.
 *
 * Usage:
 *   node walrus_uploader.js /abs/path/to/vocals.wav:/vocals.wav /abs/path/to/clean.wav:/vocals_cleaned.wav
 *   (format: sourcePath:quiltIdentifier)
 */

const fs = require('fs');
const path = require('path');

(async () => {
  try {
    const network = process.env.WALRUS_NETWORK?.trim() || 'testnet';
    const epochs = Number(process.env.WALRUS_EPOCHS || '3');
    const deletable = process.env.WALRUS_DELETABLE ? process.env.WALRUS_DELETABLE !== '0' : true;
    const uploadRelay = process.env.UPLOAD_RELAY_HOST?.trim() || null;
    const tipMax = Number(process.env.RELAY_TIP_MAX || '0');

    // ---- load SDKs (installed via package.json) ----
    const { getFullnodeUrl, SuiClient, Ed25519Keypair, fromB64, toB64 } = require('@mysten/sui');
    const { WalrusClient, WalrusFile } = require('@mysten/walrus');

    // ---- signer (Sui keypair) ----
    let keypair;
    if (process.env.SUI_PRIVATE_KEY) {
      // Accept 0x… (hex) or base64; try to normalize by removing 0x and interpreting as bytes
      const hex = process.env.SUI_PRIVATE_KEY.replace(/^0x/i, '');
      const bytes = Buffer.from(hex, 'hex');
      // Ed25519 expects 32 bytes secret seed:
      if (bytes.length !== 32 && bytes.length !== 64) {
        throw new Error('SUI_PRIVATE_KEY must be 32 or 64 bytes when decoded from hex.');
      }
      keypair = Ed25519Keypair.fromSecretKey(bytes.slice(0, 32));
    } else if (process.env.SUI_MNEMONIC) {
      // Dev convenience; for production use a proper key management flow.
      const { Ed25519Keypair: EdKp, fromDerivePath, isValidSuiMnemonic } = require('@mysten/sui/cryptography');
      const mnemonic = process.env.SUI_MNEMONIC.trim();
      if (!isValidSuiMnemonic(mnemonic)) {
        throw new Error('SUI_MNEMONIC appears invalid per Sui SDK validation.');
      }
      keypair = EdKp.deriveKeypair(mnemonic, "m/44'/784'/0'/0'/0'");
    } else {
      throw new Error('Set SUI_PRIVATE_KEY (hex) or SUI_MNEMONIC for the Walrus signer.');
    }

    // ---- Sui + Walrus clients ----
    const fullnode = process.env.SUI_FULLNODE_URL || getFullnodeUrl(network);
    const suiClient = new SuiClient({ url: fullnode });

    let walrusClient;
    if (uploadRelay) {
      // use Upload Relay (recommended)
      walrusClient = new SuiClient({ url: fullnode }).$extend(
        WalrusClient.experimental_asClientExtension({
          uploadRelay: {
            host: uploadRelay,
            sendTip: tipMax > 0 ? { max: tipMax } : undefined,
          },
        }),
      );
    } else {
      walrusClient = new WalrusClient({ network, suiClient });
    }

    // ---- collect inputs from argv ----
    // Each arg: "/abs/path/file.ext:/identifier/in/quilt"
    const pairs = process.argv.slice(2);
    if (!pairs.length) {
      throw new Error('Provide file args as sourcePath:identifier (at least one).');
    }

    const files = [];
    for (const pair of pairs) {
      const [src, ident] = pair.split(':');
      if (!src || !ident) throw new Error(`Bad arg "${pair}". Use sourcePath:identifier`);
      if (!fs.existsSync(src)) throw new Error(`File not found: ${src}`);
      const bytes = fs.readFileSync(src);
      files.push(WalrusFile.from(new Uint8Array(bytes), {
        identifier: ident,
        tags: { 'content-type': guessContentType(src) },
      }));
    }

    // ---- Write as a quilt (single blob with multiple files) ----
    const result = await new WalrusClient({ network, suiClient }).writeFiles({
      files,
      epochs,
      deletable,
      signer: keypair,
    });

    // result[] contains entries with { id, blobId, blobObject }
    // In current SDK, all written to a single quilt/blob.
    const blobId = result?.[0]?.blobId || null;
    const quiltId = result?.[0]?.id || null;

    const out = {
      ok: true,
      network,
      quiltId,
      blobId,
      files: pairs.map((p) => {
        const [src, ident] = p.split(':');
        return { path: path.resolve(src), identifier: ident };
      }),
    };
    process.stdout.write(JSON.stringify(out) + '\n');
    process.exit(0);
  } catch (e) {
    const err = { ok: false, error: String(e && e.message || e) };
    process.stdout.write(JSON.stringify(err) + '\n');
    process.exit(1);
  }
})();

function guessContentType(p) {
  const ext = (p.split('.').pop() || '').toLowerCase();
  if (ext === 'wav') return 'audio/wav';
  if (ext === 'mp3') return 'audio/mpeg';
  if (ext === 'flac') return 'audio/flac';
  return 'application/octet-stream';
}

