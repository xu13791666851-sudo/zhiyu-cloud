import requests
import traceback

DIFY_API_URL = "http://localhost:3000/v1"
DIFY_API_KEY = "dataset-cCdb0p6b63FvjB8QzUFaVVQ6"
DIFY_DATASET_ID = "07503008-cd5e-43b7-8ed1-4c32d34e5c6f"

url = f"{DIFY_API_URL}/datasets/{DIFY_DATASET_ID}/retrieve"
headers = {
    "Authorization": f"Bearer {DIFY_API_KEY}",
    "Content-Type": "application/json"
}
payload = {
    "query": "深圳建筑遗产",
    "top_k": 3
}

print(f"请求 URL: {url}")
print("发送请求中（超时 15 秒）...")

resp = requests.post(url, headers=headers, json=payload, timeout=15)
print(f"\n状态码: {resp.status_code}")
print(f"响应内容:\n{resp.text[:2000]}")
