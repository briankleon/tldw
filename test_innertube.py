import httpx

video_id = 'drescQrqOWo'
payload = {
    'context': {
        'client': {
            'clientName': 'WEB',
            'clientVersion': '2.20240313.05.00',
            'hl': 'en',
        }
    },
    'videoId': video_id,
}
headers = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

with httpx.Client(timeout=15.0) as client:
    resp = client.post('https://www.youtube.com/youtubei/v1/player', json=payload, headers=headers)
    data = resp.json()
    captions = data.get('captions', {}).get('playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
    print(f'Found {len(captions)} caption tracks')
    for c in captions[:3]:
        print(f"  - {c.get('languageCode')}: {c.get('baseUrl', '')[:80]}")
    if captions:
        cap_url = captions[0]['baseUrl']
        xml_resp = client.get(cap_url)
        print(f'Status: {xml_resp.status_code}')
        print(xml_resp.text[:300])
    else:
        print('No captions found')
        # Check if there is an error
        if 'playabilityStatus' in data:
            print(f"Playability: {data['playabilityStatus'].get('status')}")
            print(f"Reason: {data['playabilityStatus'].get('reason', 'N/A')}")

