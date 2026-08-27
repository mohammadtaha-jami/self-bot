"""Script to create the initial admin user in database."""

import asyncio
from passlib.context import CryptContext
from sqlalchemy import select

from core.database import get_session_factory
from shared.models import User

# هش‌کننده رمز عبور (در صورت داشتن تابع اختصاصی در core.security می‌توانید آن را import کنید)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_first_admin():
    session_factory = get_session_factory()
    async with session_factory() as session:
        # ۱. بررسی وجود ادمین قبلی
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print("⚠️ کاربر ادمین با نام کاربری 'admin' از قبل وجود دارد.")
            return

        # ۲. ساخت کاربر ادمین جدید
        admin = User(
            username="admin",
            hashed_password=pwd_context.hash("admin1234"),
            full_name="مدیر سیستم",
            is_admin=True,
            is_active=True,
        )

        session.add(admin)
        await session.commit()

        print("✅ کاربر ادمین اولیه با موفقیت ساخته شد.")
        print("اطلاعات ورود:")
        print("نام کاربری: admin")
        print("رمز عبور: admin1234")


if __name__ == "__main__":
    asyncio.run(create_first_admin())