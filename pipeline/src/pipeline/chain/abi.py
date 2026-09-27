"""ABI minimal: hanya event dan fungsi yang benar-benar dipakai."""


def _event(name: str, inputs: list[tuple[str, str, bool]]) -> dict:
    return {
        "type": "event",
        "name": name,
        "anonymous": False,
        "inputs": [{"name": n, "type": t, "indexed": i} for n, t, i in inputs],
    }


def _fn(name: str, inputs: list[str], outputs: list[str], view: bool = True) -> dict:
    return {
        "type": "function",
        "name": name,
        "stateMutability": "view" if view else "nonpayable",
        "inputs": [{"name": f"a{i}", "type": t} for i, t in enumerate(inputs)],
        "outputs": [{"name": "", "type": t} for t in outputs],
    }


FACTORY_ABI = [
    _event(
        "PairCreated",
        [
            ("token0", "address", True),
            ("token1", "address", True),
            ("pair", "address", False),
            ("", "uint256", False),
        ],
    )
]

PAIR_ABI = [
    _event("Sync", [("reserve0", "uint112", False), ("reserve1", "uint112", False)]),
    _event(
        "Mint",
        [("sender", "address", True), ("amount0", "uint256", False), ("amount1", "uint256", False)],
    ),
    _event(
        "Burn",
        [
            ("sender", "address", True),
            ("amount0", "uint256", False),
            ("amount1", "uint256", False),
            ("to", "address", True),
        ],
    ),
    _event(
        "Swap",
        [
            ("sender", "address", True),
            ("amount0In", "uint256", False),
            ("amount1In", "uint256", False),
            ("amount0Out", "uint256", False),
            ("amount1Out", "uint256", False),
            ("to", "address", True),
        ],
    ),
    _event(
        "Transfer",
        [("from", "address", True), ("to", "address", True), ("value", "uint256", False)],
    ),
]

ERC20_ABI = [
    PAIR_ABI[-1],
    _fn("balanceOf", ["address"], ["uint256"]),
    _fn("decimals", [], ["uint8"]),
    _fn("symbol", [], ["string"]),
    _fn("approve", ["address", "uint256"], ["bool"], view=False),
]

ROUTER_ABI = [
    _fn("WETH", [], ["address"]),
    _fn("getAmountsOut", ["uint256", "address[]"], ["uint256[]"]),
    _fn(
        "swapExactTokensForETHSupportingFeeOnTransferTokens",
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [],
        view=False,
    ),
]
