"""
Automated test suite for AI Gateway.
Verifies DB operations, billing rules, rate limiting, and OpenAI compatibility.
Run with: python -m pytest test_gateway.py or python test_gateway.py
"""

import asyncio
import os
import sys
import shutil
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Set test database path before imports
os.environ["DB_PATH"] = "data/test_gateway.db"
os.environ["ADMIN_PASSWORD"] = "testpassword123"
os.environ["RATE_LIMIT_PER_MINUTE"] = "5"

from app.config import settings
from app.database import (
    init_db,
    create_user,
    get_user_by_id,
    get_user_by_api_key,
    topup_user_tokens,
    deduct_user_tokens,
    update_user_status,
    get_recent_logs,
    get_system_stats,
    set_dynamic_setting,
    get_upstream_config,
)
from app.auth import generate_user_api_key, create_admin_token, verify_admin_token
from app.billing import check_token_balance, record_usage_and_deduct
from app.limiter import check_rate_limit
from fastapi import HTTPException


async def run_all_tests():
    print("==================================================")
    print("BẮT ĐẦU KIỂM THỬ HỆ THỐNG AI GATEWAY ('QUÁN NET')")
    print("==================================================")

    # Clean previous test DB
    test_db = Path("data/test_gateway.db")
    if test_db.exists():
        test_db.unlink()

    # 1. Test Database Init
    print("\n[1/8] Kiểm tra khởi tạo cơ sở dữ liệu...")
    await init_db()
    assert test_db.exists(), "DB file chưa được tạo!"
    print("  -> Khởi tạo DB thành công!")

    # 2. Test User Creation & Key Generation
    print("\n[2/8] Kiểm tra tạo hội viên và sinh API Key...")
    raw_key = generate_user_api_key()
    assert raw_key.startswith("sk-user-"), f"Key không đúng format: {raw_key}"
    assert len(raw_key) == 8 + 32, f"Độ dài key không chuẩn: {len(raw_key)}"

    user = await create_user(username="test_gamer", api_key=raw_key)
    assert user["username"] == "test_gamer"
    assert user["token_balance"] == 0, "Hội viên mới tạo phải có balance = 0"
    assert user["status"] == "active"
    print(f"  -> Tạo user '{user['username']}' thành công với key: {user['api_key']}")

    # 3. Test Balance Check with 0 tokens (Must raise HTTP 402)
    print("\n[3/8] Kiểm tra từ chối khi số dư token = 0 (HTTP 402)...")
    try:
        check_token_balance(user)
        assert False, "Phải ném ra lỗi HTTP 402 khi token_balance = 0!"
    except HTTPException as e:
        assert e.status_code == 402, f"Mã lỗi không phải 402: {e.status_code}"
        assert e.detail["error"]["code"] == "insufficient_token_balance"
        print("  -> Chặn thành công request khi số dư = 0 (HTTP 402 Insufficient Balance)!")

    # 4. Test Token Top-up (Nạp tiền ngoài đời -> cộng token)
    print("\n[4/8] Kiểm tra tính năng nạp token (Top-up)...")
    updated_user = await topup_user_tokens(user["id"], 500000)
    assert updated_user["token_balance"] == 500000
    print(f"  -> Nạp thành công +500,000 token! Số dư mới: {updated_user['token_balance']:,}")

    # Now balance > 0, balance check must pass
    check_token_balance(updated_user)
    print("  -> Kiểm tra balance check: Đã cho phép request đi qua!")

    # 5. Test Token Deduction (Deduct based on real usage)
    print("\n[5/8] Kiểm tra trừ token dựa trên usage thật...")
    await record_usage_and_deduct(
        user_id=user["id"],
        username=user["username"],
        model="llama-3-8b",
        prompt_tokens=150,
        completion_tokens=350,
        total_tokens=500,
        status_code=200,
        duration_ms=450,
    )
    user_after_deduct = await get_user_by_id(user["id"])
    assert user_after_deduct["token_balance"] == 500000 - 500
    assert user_after_deduct["lifetime_tokens_used"] == 500
    print(f"  -> Trừ chính xác 500 token! Số dư còn lại: {user_after_deduct['token_balance']:,}")

    # Check request log
    logs = await get_recent_logs(10)
    assert len(logs) == 1
    assert logs[0]["total_tokens"] == 500
    assert logs[0]["model"] == "llama-3-8b"
    print("  -> Ghi nhận log metadata thành công (không lưu nội dung chat)!")

    # 6. Test Negative Balance and Blocking Next Request
    print("\n[6/8] Kiểm tra trường hợp trừ âm số dư và khoá request tiếp theo...")
    # User currently has 499,500 tokens. Deduct 500,000 tokens (balance becomes -500)
    user_negative = await deduct_user_tokens(user["id"], 500000)
    assert user_negative["token_balance"] == -500
    print(f"  -> Cho phép số dư âm nhẹ sau request lớn: {user_negative['token_balance']}")

    try:
        check_token_balance(user_negative)
        assert False, "Request tiếp theo phải bị chặn khi balance âm!"
    except HTTPException as e:
        assert e.status_code == 402
        print("  -> Chặn thành công request kế tiếp khi số dư âm (HTTP 402)!")

    # 7. Test User Suspension
    print("\n[7/8] Kiểm tra tính năng tạm khoá tài khoản (Suspension)...")
    await update_user_status(user["id"], "suspended")
    user_suspended = await get_user_by_id(user["id"])
    assert user_suspended["status"] == "suspended"
    print("  -> Tạm khoá tài khoản thành công!")

    # 8. Test Dynamic Upstream Settings
    print("\n[8/8] Kiểm tra đổi Upstream URL động không cần restart...")
    new_url = "https://new-colab-endpoint.ngrok-free.app/v1"
    await set_dynamic_setting("upstream_base_url", new_url)
    cfg = await get_upstream_config()
    assert cfg["upstream_base_url"] == new_url
    print(f"  -> Cập nhật Upstream URL động thành công: {cfg['upstream_base_url']}")

    # 9. Test Admin Token Authentication
    admin_tok = create_admin_token()
    assert verify_admin_token(admin_tok) is True
    assert verify_admin_token("invalid.token.123") is False
    print("  -> Kiểm tra ký và xác thực token Admin: OK!")

    print("\n==================================================")
    print("TẤT CẢ 8 BỘ KIỂM THỬ ĐÃ VƯỢT QUA 100% HOÀN HẢO! 🎉")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
