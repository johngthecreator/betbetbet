"""Per-tool output-formatting instructions.

These aren't LangChain SystemMessages -- they're prepended directly to each
tool's ToolMessage content in call_tool() (main.py), so the model sees the
formatting instruction right next to the data it describes. That's more
reliable than a single system prompt trying to cover every tool's format at
once, and keeps call_tool() readable as more tools get added.
"""

# Appended to every format instruction below. discord_bot.py sends the
# model's whole response as a single embed, so if the model repeats itself
# (e.g. restates the list or product summary a second time in the same
# reply), the user sees that duplicate inline in one Discord message. This
# is a prompt-level stopgap -- it doesn't catch every case (e.g. two
# separately near-identical write-ups). A real fix (e.g. detecting and
# stripping duplicate content in the output before sending) is TODO --
# see README's "Known limitations".
_DEDUPE_NOTE = """
Write your answer once. Before finishing, check that you haven't repeated \
the same sentence, list, or summary twice in this reply -- if you have, \
remove the duplicate and send it only once.
"""

GET_PRODUCT_DETAIL_FORMAT = """\
Format the product data below for the user. Always include:
- A link to the product.
- Current price, original price, and how much it's on sale by (amount and/or percent off).
- Available sizes, and separately, sizes that are NOT available, if that's in the data.
- Available colors.
- A short note at the end for anything else notable you noticed in the data \
(e.g. limited colorways, low stock, a size guide callout) -- only include this \
if there's actually something worth mentioning, don't force it.
""" + _DEDUPE_NOTE + """
Product data:
"""

GRAB_SALES_FORMAT = """\
Format the product data below as a numbered list, one product per line. For \
each product, show only its name and current price -- do not show the URL \
to the user. The URLs are included in the data below so you can look up the \
right one later, once the user picks a number.

Tell the user they can reply with a product's number to get full details on \
it (sizes, colors, price breakdown, etc.).

Return this as plain numbered text, not a table.
""" + _DEDUPE_NOTE + """
Product data:
"""
