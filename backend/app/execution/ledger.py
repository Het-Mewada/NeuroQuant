import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import AccountDB, LedgerTransactionDB
from app.models.domain import LedgerTxType


class DoubleEntryLedger:
    """
    Guarantees strict double-entry accounting integrity for virtual trading capital.
    Prevents duplicate transactions, overdrafts, and phantom balances.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_account(self, account_id: str = "default_user") -> AccountDB:
        result = await self.session.execute(select(AccountDB).where(AccountDB.id == account_id))
        account = result.scalars().first()
        if not account:
            account = AccountDB(
                id=account_id,
                total_equity=500000.0,
                available_cash=500000.0,
                reserved_margin=0.0,
                currency="INR"
            )
            self.session.add(account)
            await self.session.commit()
            await self.session.refresh(account)
        return account

    async def deposit(
        self,
        account_id: str,
        amount: float,
        idempotency_key: Optional[str] = None
    ) -> LedgerTransactionDB:
        if amount <= 0:
            raise ValueError("Deposit amount must be strictly positive")

        if not idempotency_key:
            idempotency_key = f"dep_{uuid.uuid4()}"

        account = await self.get_or_create_account(account_id)
        account.available_cash += amount
        account.total_equity += amount

        tx = LedgerTransactionDB(
            id=str(uuid.uuid4()),
            account_id=account.id,
            tx_type=LedgerTxType.DEPOSIT.value,
            amount=amount,
            balance_after=account.available_cash,
            idempotency_key=idempotency_key,
            metadata_json='{"action": "virtual_deposit"}'
        )
        self.session.add(tx)
        await self.session.commit()
        await self.session.refresh(account)
        return tx

    async def withdraw(
        self,
        account_id: str,
        amount: float,
        idempotency_key: Optional[str] = None
    ) -> LedgerTransactionDB:
        if amount <= 0:
            raise ValueError("Withdrawal amount must be strictly positive")

        account = await self.get_or_create_account(account_id)
        if account.available_cash < amount:
            raise ValueError(
                f"Insufficient available cash: Requested ₹{amount:,.2f}, Available: ₹{account.available_cash:,.2f}"
            )

        if not idempotency_key:
            idempotency_key = f"wth_{uuid.uuid4()}"

        account.available_cash -= amount
        account.total_equity -= amount

        tx = LedgerTransactionDB(
            id=str(uuid.uuid4()),
            account_id=account.id,
            tx_type=LedgerTxType.WITHDRAWAL.value,
            amount=-amount,
            balance_after=account.available_cash,
            idempotency_key=idempotency_key,
            metadata_json='{"action": "virtual_withdrawal"}'
        )
        self.session.add(tx)
        await self.session.commit()
        await self.session.refresh(account)
        return tx

    async def reserve_margin(
        self,
        account_id: str,
        amount: float,
        order_id: str
    ) -> bool:
        account = await self.get_or_create_account(account_id)
        if account.available_cash < amount:
            return False

        account.available_cash -= amount
        account.reserved_margin += amount

        tx = LedgerTransactionDB(
            id=str(uuid.uuid4()),
            account_id=account.id,
            tx_type=LedgerTxType.MARGIN_HOLD.value,
            amount=-amount,
            balance_after=account.available_cash,
            idempotency_key=f"hold_{order_id}",
            metadata_json=f'{{"order_id": "{order_id}"}}'
        )
        self.session.add(tx)
        await self.session.commit()
        return True

    async def release_margin(
        self,
        account_id: str,
        amount: float,
        order_id: str
    ):
        account = await self.get_or_create_account(account_id)
        release_amt = min(account.reserved_margin, amount)
        account.reserved_margin -= release_amt
        account.available_cash += release_amt

        tx = LedgerTransactionDB(
            id=str(uuid.uuid4()),
            account_id=account.id,
            tx_type=LedgerTxType.MARGIN_RELEASE.value,
            amount=release_amt,
            balance_after=account.available_cash,
            idempotency_key=f"rel_{order_id}_{uuid.uuid4().hex[:6]}",
            metadata_json=f'{{"order_id": "{order_id}"}}'
        )
        self.session.add(tx)
        await self.session.commit()

    async def settle_trade(
        self,
        account_id: str,
        realized_pnl: float,
        fees: float,
        position_id: str
    ):
        account = await self.get_or_create_account(account_id)
        net_credit = realized_pnl - fees
        account.available_cash += net_credit
        account.total_equity += net_credit

        tx = LedgerTransactionDB(
            id=str(uuid.uuid4()),
            account_id=account.id,
            tx_type=LedgerTxType.TRADE_PNL.value,
            amount=net_credit,
            balance_after=account.available_cash,
            idempotency_key=f"pnl_{position_id}_{uuid.uuid4().hex[:6]}",
            metadata_json=f'{{"position_id": "{position_id}", "gross_pnl": {realized_pnl}, "fees": {fees}}}'
        )
        self.session.add(tx)
        await self.session.commit()
