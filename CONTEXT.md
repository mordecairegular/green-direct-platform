# Green Direct Planning Context

This context defines the domain language for the green direct power and microgrid planning platform. It keeps business terms separate from implementation details so recommendation, economy, reports, and UI use the same vocabulary.

## Language

**Project Investment Structure**:
The ownership and commercial relationship between renewable generation, storage, grid connection assets, and the consuming load. A project may use a **Single-Entity Structure** or a **Two-Entity Structure**.
_Avoid_: Scenario type when referring to ownership; dispatch mode when referring to commercial structure.

**Single-Entity Structure**:
A project structure where the same investment subject owns or controls both the power-side assets and the load-side consumption interest. The economic question is whether the incremental green direct power investment maximizes whole-project incremental benefit.
_Avoid_: Owner-user integrated project, one-body project.

**Two-Entity Structure**:
A project structure where the power-side investor and the load-side user are different subjects. The economic question must be split between power-side investment return and load-side energy procurement or environmental-value benefit.
_Avoid_: Separate-owner project, split project.

**Power-Side Investor**:
The subject that invests in power-side assets such as wind, PV, BESS, and dedicated connection lines. In a **Two-Entity Structure**, this subject mainly evaluates investment return from selling or settling green electricity and related revenues.
_Avoid_: Generator when the subject may also own storage or connection assets.

**Load-Side User**:
The subject that consumes electricity and evaluates how green direct power changes its energy cost, green power share, and optional environmental-value benefits compared with grid purchase. In a **Two-Entity Structure**, this subject may care about green certificate or carbon-related value, but those benefits should be explicit optional assumptions.
_Avoid_: Customer when the role specifically means electricity consumer.

**Incremental Green Direct Power Investment**:
The additional investment and operating arrangement introduced by adding green direct power to a baseline energy supply pattern. It is evaluated by comparing incremental cost, savings, revenue, and optional environmental value against the no-project or grid-purchase baseline.
_Avoid_: Total project cost when the analysis is explicitly incremental.

**Avoided Grid Purchase Benefit**:
The economic benefit created when renewable self-use reduces external grid purchase under a **Single-Entity Structure**. It should be based on the avoided external purchase cost, not on an internal green power settlement price.
_Avoid_: Internal sale revenue in a single-entity consolidated view.

**Net Avoided Grid Cost Price**:
The unit price used to value **Avoided Grid Purchase Benefit** after removing cost components that are not treated as avoidable in the active model and after excluding deductible VAT where applicable. It is a planning-model assumption and should be reported with its simplification boundary.
_Avoid_: Total electricity bill divided by total load.

**Dedicated Connection Line Investment**:
The Year 0 investment for the power delivery line or dedicated connection works required to connect the power-side assets to the load-side project or grid connection point. It is a required green direct project cost driver and should be modeled separately from **Other Fixed Asset Investment**. In the first version, users enter the total amount with VAT directly.
_Avoid_: Other fixed asset investment.

**Other Fixed Asset Investment**:
Year 0 fixed asset investment that is not already represented by wind, PV, BESS, or **Dedicated Connection Line Investment**. It may remain a user-entered total amount for miscellaneous project assets.
_Avoid_: Catch-all for required line connection works.

**Environmental-Value Benefit**:
Optional value associated with green electricity attributes, such as green certificates, carbon-related savings, or other user-defined environmental income or avoided cost. The exact policy term should be named explicitly once confirmed for the project jurisdiction and use case.
_Avoid_: Carbon tax as a generic placeholder.

**Green Power Settlement Price**:
The price used to settle green electricity self-used by the load. For the **Power-Side Investor**, it is revenue. For the **Load-Side User**, it is procurement cost. For a **Single-Entity Structure**, it should not be double-counted as internal revenue. In Chinese UI text, this may be explained as the self-use electricity settlement price.
_Avoid_: Self-use price when the role of the price is unclear.

**Load Grid Purchase Price**:
The price the load would pay for electricity purchased from the grid under the baseline or remaining grid-purchase arrangement. It is the comparison price for load-side savings and the starting input for single-entity avoided purchase cost. The default simple input for single-entity analysis is **Net Avoided Grid Cost Price**. If the user enables bill build-up mode, user-facing fields should match bill items such as energy/market purchase price, line-loss fee, system operation fee, transmission and distribution tariff, and government fund surcharge.
_Avoid_: Export price; green power settlement price.

**Recommendation Perspective**:
The economic or engineering viewpoint used to select and rank scenarios, such as whole-project incremental benefit, power-side investment return, or load-side energy benefit. The default recommendation portfolio may include scenarios from multiple perspectives without forcing the user to choose one first.
_Avoid_: Advanced parameter when referring to the business viewpoint itself.

**Perspective-Specific Ranking**:
An advanced ranking mode where the user focuses on one **Recommendation Perspective** and reviews best, second-best, and lower-ranked scenarios under that perspective. It is a drill-down mode, not the default recommendation experience.
_Avoid_: Default recommendation when referring to a single-viewpoint ranking list.

**Policy-Compliant Minimum-Investment Scenario**:
A scenario that satisfies the active policy and feasibility constraints while minimizing upfront investment. It is useful across investment structures because all parties care about the least-capital path to compliance.
_Avoid_: Cheapest scenario when the metric specifically means initial investment rather than lifecycle cost or net present value.

**Policy-Compliant Candidate Set**:
The scenario set eligible for recommendation after applying active policy and feasibility constraints. Default recommendation slots should rank within this set; non-compliant scenarios belong in diagnostics or sensitivity review, not ordinary recommendation ranking.
_Avoid_: Ranking failed scenarios together with compliant recommendation candidates.

**High Self-Use Scenario**:
A scenario that maximizes renewable self-use rate, where self-use is renewable energy consumed by the load either directly or through renewable-charged BESS. Under green direct policy export caps, it is related to but still not identical to **Low-Curtailment Scenario** because export within the cap, storage losses, and final stored energy can change curtailment without equally changing self-use delivered to load.
_Avoid_: High consumption when the denominator is unclear.

**High Green-Load Scenario**:
A scenario that maximizes the share of load served by renewable self-use. It is different from **High Self-Use Scenario** because the denominator is total load rather than total renewable generation.
_Avoid_: High green scenario.

**Low-Curtailment Scenario**:
A scenario that minimizes curtailed renewable energy. It measures unused available renewable generation and should not be conflated with self-use or load-side green share, especially when capped export, BESS losses, or year-end SOC differences exist.
_Avoid_: High consumption scenario.

**Power-Side Investment Return Scenario**:
A recommendation slot that selects the scenario with the strongest return for the **Power-Side Investor** under the active power-side economic model. In the current V1 economy model, the default ranking should prioritize FIRR, with FNPV and payback as supporting indicators, because early green direct projects often care most about fast capital recovery and risk resilience. Current V1 uses annual average settlement prices and should later support time-resolved settlement price profiles.
_Avoid_: Overall best scenario when only the power-side perspective is being evaluated.

**Power-Side FIRR Ranking**:
A perspective-specific ranking rule for the current **Power-Side Investment Return Scenario**. It first keeps policy-compliant scenarios with reliable FIRR, then sorts by higher FIRR, shorter static payback, shorter dynamic payback, and higher FNPV.
_Avoid_: NPV-first ranking when describing the default power-side V1 recommendation.

**Load-Side Benefit Scenario**:
A recommendation slot that selects the scenario most beneficial to the **Load-Side User**, considering green electricity received, comparison between **Load Grid Purchase Price** and **Green Power Settlement Price**, and optional **Environmental-Value Benefit** assumptions. When the load side bears no initial investment, this scenario should be ranked by annual or lifecycle energy benefit rather than FIRR. The first version may use fixed prices, but the concept must allow hourly or sub-hourly price profiles.
_Avoid_: Consumer saving scenario when environmental value is included.

**Time-Resolved Price Profile**:
A price input series aligned to the simulation time step, such as 8760 hourly prices or future 15-minute prices. It may apply to grid purchase, export settlement, green power settlement, or other market-linked energy values. **Environmental-Value Benefit** is currently treated as a scalar user assumption rather than a time-resolved profile.
_Avoid_: TOU tariff when the profile may be arbitrary or sub-hourly.

**Spreadsheet-Prepared Input**:
Project input data or derived parameters prepared in CSV or Excel before entering the app. When a transformation is clearer and more auditable in a spreadsheet than in web controls, the platform should accept the prepared input rather than forcing the workflow into the UI.
_Avoid_: UI setting when the value is better maintained as tabular project data.

## Example Dialogue

Expert: "Who owns the renewable assets and who consumes the power?"

Developer: "If it is a Single-Entity Structure, the recommendation should optimize whole-project incremental benefit. If it is a Two-Entity Structure, we should show the Power-Side Investor return separately from the Load-Side User benefit."

Expert: "Does the load user count green certificates?"

Developer: "Only if the user enables Environmental-Value Benefit assumptions. Otherwise the load-side view compares green direct power settlement cost with grid purchase and reports green power share."

Expert: "Should the user choose the investment structure before seeing recommendations?"

Developer: "No. The default portfolio should surface useful scenarios from multiple Recommendation Perspectives. If the user wants to focus on only the power-side or load-side view, they can use Perspective-Specific Ranking."

Expert: "Is a low-curtailment scenario the same as a high self-use scenario when export is capped?"

Developer: "No, though they are more closely related under an export cap. Low-Curtailment minimizes unused renewable energy, while High Self-Use maximizes renewable energy actually delivered to load; capped export, BESS losses, and final SOC can still make the winners different."

Expert: "Can the first economy model use annual average prices?"

Developer: "Yes, but the recommendation language should say this is the current power-side V1 economy model. The domain model should reserve Time-Resolved Price Profiles for export, self-use, and grid purchase prices."

Expert: "Should every uncertain preprocessing step become a web form?"

Developer: "No. If the project team can prepare it more clearly in CSV or Excel, use Spreadsheet-Prepared Input and keep the UI focused on review, diagnostics, and decision-making."
