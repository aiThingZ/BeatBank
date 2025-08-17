#!/bin/bash
set -e

INPUT_DIR="./input"
OUTPUT_DIR="./output"
CLEANED_DIR="./output_cleaned"

mkdir -p "$OUTPUT_DIR" "$CLEANED_DIR"

for input_file in "$INPUT_DIR"/*.{mp3,mp4,wav}; do
  [ -e "$input_file" ] || continue

  base=$(basename "$input_file")
  stem="${base%.*}"

  echo "▶️ Processing: $base"

  # Step 1: Convert to wav (optional; not used by demucs call below, but kept)
  ffmpeg -y -i "$input_file" -ar 44100 -ac 2 "/tmp/$stem.wav"

  # Step 2: Run Demucs for vocals only
  #docker run --rm --gpus all \
  docker run --rm  \
    -v "$(pwd)/$INPUT_DIR":/data/input \
    -v "$(pwd)/$OUTPUT_DIR":/data/output \
    demucs-gpu \
    python3 -m demucs -n htdemucs_ft --two-stems=vocals \
    --segment 6 --overlap 0.25 -j 1 \
    --out /data/output "/data/input/$base"

  # Step 3: Apply basic EQ cleanup
  VFILE="$OUTPUT_DIR/htdemucs_ft/$stem/vocals.wav"
  CLEANED="$CLEANED_DIR/${stem}_vocals_cleaned.wav"

  ffmpeg -y -i "$VFILE" \
    -af "highpass=f=80, lowpass=f=8000, dynaudnorm" \
    "$CLEANED"

  echo "✅ Saved cleaned vocals to $CLEANED"
done

