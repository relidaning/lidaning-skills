# Compositions

**Problem:** You have real savings and want to invest them yourself — but stock
tips, fund salespeople, and your own FOMO all want your money, and the majority
of A-share retail investors lose theirs. The fix isn't a magic stock pick; it's
a disciplined personal-investing workflow on Python's standard quant stack
(akshare data → pandas analysis → backtesting.py/vectorbt verification) plus
behavioral rules that keep you in the game. Each leaf is one concrete,
real-life issue — the teaching unit.

1. **Get your money facts straight** *(besmart task #85)*
   - **You have savings AND credit-card debt — should you invest at all yet?**
     *(leaf #91)* — emergency fund first (3–6 months expenses), clear
     high-interest debt before investing, net-worth snapshot
   - **You can't sleep when the market drops 10% — what happens at −40%?**
     *(leaf #92)* — risk-tolerance test, investment horizon, the A-share
     drawdown reality (2015 crash, 2018 bear)
   - **"Just make money" isn't a plan** *(leaf #93)* — a one-page investment
     policy: goal amount, horizon, monthly contribution, crash behavior
2. **Choose the right products from the risk ladder** *(besmart task #86)*
   - **Your bank savings account is losing to inflation** *(leaf #94)* —
     deposits → 货币基金(余额宝) → 债基 → 宽基指数基金 → 个股; real return =
     nominal − inflation
   - **Fund fees and taxes quietly eat your returns** *(leaf #95)* — 管理费/
     申购赎回费/销售服务费, 印花税/佣金, why a 1% fee compounds against you
   - **A salesperson pushes a "稳赚不赔" wealth product** *(leaf #96)* — read
     the product spec; guaranteed-high-return is a red flag; unregulated
     products (the P2P lesson)
3. **Read a stock like an analyst** *(besmart task #87)*
   - **You only see the price, not the company** *(leaf #97)* — akshare
     quotes/history/financials into pandas; first company dashboard
   - **"PE 5 = cheap, PE 50 = expensive" — what do these numbers actually tell
     you?** *(leaf #98)* — PE/PB/ROE/股息率, growth vs cyclical, value traps
   - **The company's "profit" might be fake** *(leaf #99)* — revenue vs net
     profit vs operating cash flow; red flags (应收账款, 商誉, 质押率)
   - **A hot-tip stock looks great on a chart** *(leaf #100)* — why most
     A-share retail lose: info asymmetry, hot sectors, indicators ≠ edge
4. **Build a portfolio you can hold through a crash** *(besmart task #88)*
   - **You don't know how to split safe vs risky** *(leaf #101)* — asset
     allocation by horizon/risk — matters more than picking "the best" stock
   - **You pick 5 hot stocks and they all crash together** *(leaf #102)* —
     correlation & diversification; 沪深300/中证500 broad index funds as core
   - **Lump sum or monthly?** *(leaf #103)* — 定投 (DCA) vs lump sum: the
     smile curve, why it fits A-share volatility and salary income
   - **Set it and forget it — but the portfolio drifts** *(leaf #104)* —
     rebalancing (calendar/threshold), benchmarking vs 沪深300
5. **Know and control your risk** *(besmart task #89)*
   - **A 30% drawdown makes you sell at the bottom** *(leaf #105)* — volatility/
     drawdown stats, why they're normal, hold-through vs timing
   - **You go all-in on one trade** *(leaf #106)* — position sizing & 仓位
     rules, single-position cap, cash buffer
   - **Options and hedging sound smart — are they for you?** *(leaf #107)* —
     your position/hedge/option definitions in context, the cost of hedging,
     why beginners avoid derivatives; stop-loss discipline
   - **融资/杠杆 sounds like free money** *(leaf #108)* — margin calls & 爆仓
     (liquidation), why leverage turns a small dip into account death
6. **Verify a strategy before risking real money** *(besmart task #90)*
   - **Your idea "seems good" but you have no evidence** *(leaf #109)* —
     backtest with akshare + backtesting.py/vectorbt: 定投 vs lump-sum on
     沪深300, including 印花税 and fees
   - **The backtest returns 300% — too good to be true** *(leaf #110)* —
     overfitting, look-ahead bias, survivorship bias, out-of-sample validation
   - **股吧 is shouting about one stock** *(leaf #111)* — the FOMO/herding/
     confirmation loop; a one-page trading checklist
