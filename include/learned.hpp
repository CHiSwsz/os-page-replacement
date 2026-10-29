#pragma once
#include "paging.hpp"

namespace paging {
// V5 evaluates 25 past-only experts, including V4's seven experts. All shadow
// caches store page identifiers, not page contents. Only the requested page is
// admitted to the one physical cache on a miss.
constexpr std::size_t learned_expert_count = 25;
struct LearnedDiagnostics {
    std::array<std::size_t, learned_expert_count> expert_uses{};
    std::array<std::size_t, learned_expert_count> expert_faults{};
    std::size_t model_peak = 0;
};
class OnlineAdaptiveV5 {
    struct Impl;
    std::unique_ptr<Impl> impl_;
public:
    explicit OnlineAdaptiveV5(std::size_t capacity, std::uint64_t seed = 0,
                              AdaptiveOptions options = {4, 16, 5});
    ~OnlineAdaptiveV5();
    OnlineAdaptiveV5(OnlineAdaptiveV5&&) noexcept;
    OnlineAdaptiveV5& operator=(OnlineAdaptiveV5&&) noexcept;
    OnlineAdaptiveV5(const OnlineAdaptiveV5&) = delete;
    OnlineAdaptiveV5& operator=(const OnlineAdaptiveV5&) = delete;
    Event access(Page page);
    // Result's seven expert counters remain the V4 expert subset. Use
    // diagnostics() for all 25; policy_uses still covers every request.
    const Result& result() const;
    const LearnedDiagnostics& diagnostics() const;
};
Result simulate_v5(const std::vector<Page>& trace, std::size_t capacity,
                   std::uint64_t seed, bool record_events, AdaptiveOptions options);
} // namespace paging
