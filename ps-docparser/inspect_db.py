import sqlite3
import json

conn = sqlite3.connect('.cache/table_cache.db')
c = conn.cursor()
c.execute('SELECT value FROM cache')
for row in c.fetchall():
    data_str = row[0]
    if "LINE NO" in data_str or "REMARKS" in data_str:
        data = json.loads(data_str)
        # Check all layout details
        for page in data.get('data', {}).get('pages', []):
            for layout in page.get('layout_details', []):
                text = layout.get('text', '')
                if 'LINE NO' in text or 'REMARKS' in text or '450A' in text:
                    print(f"Found keyword in label: {layout.get('label')}")
                    print(f"Text: {text[:100]}")
