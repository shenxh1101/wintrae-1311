import urllib.request
import json

print("=== 验证异常记录查询 ===")
r = urllib.request.urlopen(
    "http://localhost:8000/api/exceptions/?exception_type=blacklist_intercept&visit_date=2026-06-18"
)
d = json.loads(r.read().decode())
print("总数:", d["total"])
for i in d["items"]:
    print(f"  - {i['visitor_name']} ({i['exception_type']}): {i['exception_reason']}")
    print(f"    处理状态: {i['handling_status']}, 处理人: {i['handler']}")

print()
print("=== 异常类型列表 ===")
r2 = urllib.request.urlopen("http://localhost:8000/api/exceptions/types")
print(json.dumps(json.loads(r2.read().decode()), ensure_ascii=False, indent=2))

print()
print("=== 黑名单操作日志 ===")
r3 = urllib.request.urlopen("http://localhost:8000/api/blacklist/logs/all")
logs = json.loads(r3.read().decode())
print(f"共 {len(logs)} 条操作记录")
for log in logs:
    print(f"  - {log['name']} ({log['id_last_four']}): {log['operation_type']} by {log['operator_name']} - {log['reason']}")

print()
print("=== 黑名单详情（含操作日志）===")
r4 = urllib.request.urlopen("http://localhost:8000/api/blacklist/1")
detail = json.loads(r4.read().decode())
print(f"姓名: {detail['name']}, 证件后四位: {detail['id_last_four']}")
print(f"操作日志数: {len(detail['operation_logs'])}")
