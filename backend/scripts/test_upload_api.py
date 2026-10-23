import httpx
from pathlib import Path

def main():
    client = httpx.Client(timeout=60.0)
    img_path = Path("testset/images/rx_001.png")

    if not img_path.exists():
        img_path = Path("../testset/images/rx_001.png")

    if not img_path.exists():
        print(f"Error: test image {img_path} not found.")
        return

    with open(img_path, "rb") as f:
        files = {"file": ("rx_001.png", f, "image/png")}
        r = client.post("http://127.0.0.1:8000/api/prescriptions/upload", files=files)

    print("Status Code:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print("Rx ID:", data.get("rx_id"))
        print("QC Passed:", data.get("qc", {}).get("passed"))
        print(f"Total lines extracted: {len(data.get('lines', []))}")
        for l in data.get("lines", []):
            lid = l.get("line_id")
            guesses = l.get("guesses")
            matched = l.get("match", {}).get("drug")
            score = l.get("match", {}).get("score")
            badge = l.get("confidence", {}).get("badge")
            dose = l.get("dose_raw")
            freq = l.get("validation", {}).get("std_frequency")
            print(f"  Line {lid}: {guesses} -> {matched} ({score}%) | Dose: {dose} | Freq: {freq} | Badge: {badge}")
    else:
        print("Error:", r.text)

if __name__ == "__main__":
    main()
