import urllib.request
import urllib.parse
import json

print("=== 第1步：移出黑名单 ===")
params = urllib.parse.urlencode({
    "operator_name": "Security Li",
    "remove_reason": "appeal approved",
})
req = urllib.request.Request(
    f"http://localhost:8000/api/blacklist/1?{params}",
    method="DELETE",
)
r = urllib.request.urlopen(req)
result = json.loads(r.read().decode())
print(result["message"])

print()
print("=== 第2步：再次加入黑名单 ===")
data = json.dumps({
    "name": "测试员",
    "id_last_four": "1111",
    "reason": "second violation",
    "added_by": "Security Zhang",
}).encode()
req = urllib.request.Request(
    "http://localhost:8000/api/blacklist/",
    data=data,
    headers={"Content-Type": "application/json"},
)
r = urllib.request.urlopen(req)
result = json.loads(r.read().decode())
print(result["message"], "| operation_type:", result["data"]["operation_type"])

print()
print("=== 第3步：查看全部操作日志 ===")
r3 = urllib.request.urlopen("http://localhost:8000/api/blacklist/logs/all")
logs = json.loads(r3.read().decode())
print(f"共 {len(logs)} 条操作记录")
for log in logs:
    print(f"  [{log['created_at']}] {log['operation_type']:8s} - {log['name']} by {log['operator_name']}: {log['reason']}")
