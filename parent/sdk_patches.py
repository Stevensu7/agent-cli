"""SDK patches for the hyperliquid-python-sdk."""
from __future__ import annotations
import logging

log = logging.getLogger("sdk_patches")
_spot_meta_patched = False


def patch_spot_meta_indexing():
    """Patch hyperliquid SDK to handle:
    1. IndexError — out-of-bounds token indices on testnet
    2. KeyError — unknown HIP-3 DEX names (e.g. 'tradexyz') on testnet
    """
    global _spot_meta_patched
    if _spot_meta_patched:
        return
    _spot_meta_patched = True

    try:
        import hyperliquid.info as info_mod
        import hyperliquid.exchange as ex_mod
    except ImportError:
        log.debug("hyperliquid SDK not installed, skipping patch")
        return

    # Patch Info.__init__ for IndexError (spot_meta padding)
    _orig_info_init = info_mod.Info.__init__

    def _patched_info_init(self, *args, **kwargs):
        try:
            _orig_info_init(self, *args, **kwargs)
        except IndexError:
            log.warning("SDK spot_meta index error — applying fallback")
            spot_meta = _fetch_spot_meta(args, kwargs)
            _pad_tokens(spot_meta)
            args_list = list(args)
            while len(args_list) <= 4:
                args_list.append(None)
            args_list[4] = spot_meta
            # Clear perp_dexs from kwargs to avoid "multiple values"
            kwargs.pop("perp_dexs", None)
            if len(args_list) > 5 and isinstance(args_list[5], list):
                args_list[5] = [p for p in args_list[5] if p == ""]
            _orig_info_init(self, *args_list, **kwargs)
        except KeyError as exc:
            # Remove unknown HIP-3 DEX names from perp_dexs before Info init
            log.warning(f"SDK KeyError ({exc}) — filtering perp_dexs")
            args_list = list(args)
            if len(args_list) > 5 and isinstance(args_list[5], list):
                args_list[5] = [p for p in args_list[5] if p == ""]
            else:
                kwargs["perp_dexs"] = [p for p in kwargs.get("perp_dexs", []) if p == ""]
            _orig_info_init(self, *args_list, **kwargs)

    info_mod.Info.__init__ = _patched_info_init

    # Patch Exchange.__init__ to filter perp_dexs before passing to Info
    _orig_exchange_init = ex_mod.Exchange.__init__

    def _patched_exchange_init(self, *args, **kwargs):
        # Filter 'tradexyz' / unknown HIP-3 DEX names from perp_dexs
        perp_dexs = kwargs.get("perp_dexs")
        if perp_dexs is None and len(args) > 7:
            perp_dexs = args[7]
        if isinstance(perp_dexs, list):
            known_perp_dexs = [p for p in perp_dexs if p == ""]
            if known_perp_dexs != perp_dexs:
                log.warning(f"Filtering unknown perp_dexs from Exchange init: {perp_dexs} -> {known_perp_dexs}")
            if len(args) > 7:
                args = list(args)
                args[7] = known_perp_dexs
            else:
                kwargs["perp_dexs"] = known_perp_dexs
        _orig_exchange_init(self, *args, **kwargs)

    ex_mod.Exchange.__init__ = _patched_exchange_init
    log.debug("Applied spot_meta + KeyError patches to hyperliquid SDK")


def _fetch_spot_meta(args, kwargs):
    from hyperliquid.api import API
    base_url = args[0] if args else kwargs.get("base_url")
    timeout = kwargs.get("timeout")
    api = API(base_url, timeout)
    return api.post("/info", {"type": "spotMeta"})


def _pad_tokens(spot_meta):
    tokens = spot_meta["tokens"]
    max_idx = max(
        (idx for si in spot_meta["universe"] for idx in si["tokens"]),
        default=0,
    )
    while len(tokens) <= max_idx:
        tokens.append({
            "name": f"UNKNOWN-{len(tokens)}",
            "szDecimals": 0,
            "weiDecimals": 0,
            "index": len(tokens),
            "tokenId": "0x0",
            "isCanonical": False,
        })
