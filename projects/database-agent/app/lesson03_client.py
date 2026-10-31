import httpx

with httpx.stream(
    "POST",
    "http://127.0.0.1:8000/chat/stream",
    json={"message": "用中文解释数据库索引，并举两个例子"},
    timeout=90,
) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        print(line, flush=True)
