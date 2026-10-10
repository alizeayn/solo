"""Settings repository (key/value, with encrypted secret values)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AppSetting


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> AppSetting | None:
        return await self.session.get(AppSetting, key)

    async def all(self) -> list[AppSetting]:
        result = await self.session.execute(select(AppSetting))
        return list(result.scalars().all())

    async def set(self, key: str, value: str | None, *, is_secret: bool) -> AppSetting:
        record = await self.session.get(AppSetting, key)
        if record is None:
            record = AppSetting(key=key, value=value, is_secret=is_secret)
            self.session.add(record)
        else:
            record.value = value
            record.is_secret = is_secret
        await self.session.flush()
        return record

    async def delete(self, key: str) -> None:
        await self.session.execute(delete(AppSetting).where(AppSetting.key == key))
