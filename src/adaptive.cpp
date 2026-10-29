#include "paging.hpp"

#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <list>
#include <random>
#include <stdexcept>
#include <unordered_map>

namespace paging {
namespace {
enum class Policy : std::size_t { Random = 0, Lru = 1, Predict = 2 };

std::size_t scaled_limit(std::size_t capacity, std::size_t factor) {
    if (factor == 0 || factor > 64) throw std::invalid_argument("adaptive factors must be in [1, 64]");
    const auto maximum = std::numeric_limits<std::size_t>::max();
    return std::max(std::size_t{32}, capacity > maximum / factor ? maximum : capacity * factor);
}

// Bounded metadata for recently observed page IDs, including evicted pages.
// There are no cached page contents here and no reads of the trace suffix.
class History {
    struct Record {
        std::size_t last;
        double gap = 0;
        double deviation = 0;
        bool repeated = false;
        std::list<Page>::iterator position;
    };
    std::size_t limit_;
    bool fast_;
    std::list<Page> order_;
    std::unordered_map<Page, Record> records_;
public:
    History(std::size_t limit, bool fast) : limit_(limit), fast_(fast) {}
    std::size_t size() const { return records_.size(); }

    void observe(Page page, std::size_t now) {
        const auto found = records_.find(page);
        if (found != records_.end()) {
            auto& record = found->second;
            const double gap = static_cast<double>(now - record.last);
            if (record.repeated) {
                if (fast_) {
                    record.gap = 0.5 * record.gap + 0.5 * gap;
                } else {
                    record.deviation = 0.75 * record.deviation + 0.25 * std::abs(gap - record.gap);
                    record.gap = 0.75 * record.gap + 0.25 * gap;
                }
            } else {
                record.gap = gap;
                record.repeated = true;
            }
            record.last = now;
            order_.splice(order_.end(), order_, record.position);
        } else {
            if (records_.size() == limit_) {
                records_.erase(order_.front());
                order_.pop_front();
            }
            order_.push_back(page);
            records_.emplace(page, Record{now, 0, 0, false, std::prev(order_.end())});
        }
    }

    double delay(Page page, std::size_t now) const {
        const auto found = records_.find(page);
        if (found == records_.end() || !found->second.repeated) {
            return std::numeric_limits<double>::infinity();
        }
        const auto& record = found->second;
        const double age = static_cast<double>(now - record.last);
        const double estimate = record.gap + (fast_ ? 0 : record.deviation);
        // Unseen/one-use pages receive no protection. An overdue prediction
        // loses protection as it ages, rather than pinning a formerly hot page.
        return age < estimate ? estimate - age : age;
    }
};

class Cache {
    struct Entry { Page page; std::size_t last; };
    std::size_t capacity_;
    std::vector<Entry> frames_;
    std::unordered_map<Page, std::size_t> resident_;
    std::mt19937_64 random_;

    std::size_t random_slot() {
        const auto bound = static_cast<std::uint64_t>(frames_.size());
        const std::uint64_t threshold = (std::uint64_t{0} - bound) % bound;
        std::uint64_t draw;
        do { draw = random_(); } while (draw < threshold);
        return static_cast<std::size_t>(draw % bound);
    }
public:
    Cache(std::size_t capacity, std::uint64_t seed) : capacity_(capacity), random_(seed) {}

    Event access(Page page, std::size_t now, Policy policy, const History& history) {
        const auto found = resident_.find(page);
        if (found != resident_.end()) {
            frames_[found->second].last = now;
            return Event{now + 1, page, true, found->second, {}};
        }
        std::optional<Page> victim;
        std::size_t slot = frames_.size();
        if (frames_.size() < capacity_) {
            frames_.push_back(Entry{page, now});
        } else {
            slot = 0;
            if (policy == Policy::Random) {
                slot = random_slot();
            } else {
                double best_delay = history.delay(frames_[0].page, now);
                for (std::size_t j = 1; j < frames_.size(); ++j) {
                    const double delay = policy == Policy::Predict ? history.delay(frames_[j].page, now) : 0;
                    const bool older = frames_[j].last < frames_[slot].last;
                    if ((policy == Policy::Lru && older) ||
                        (policy == Policy::Predict && (delay > best_delay || (delay == best_delay && older)))) {
                        slot = j;
                        best_delay = delay;
                    }
                }
            }
            victim = frames_[slot].page;
            resident_.erase(*victim);
            frames_[slot] = Entry{page, now};
        }
        resident_[page] = slot;
        return Event{now + 1, page, false, slot, victim};
    }
};
}  // namespace

Result simulate_adaptive(const std::vector<Page>& trace, std::size_t capacity,
                         std::uint64_t seed, bool record_events, AdaptiveOptions options) {
    if (capacity == 0) throw std::invalid_argument("frame count must be positive");
    if (options.version < 1 || options.version > 4) throw std::invalid_argument("adaptive version must be 1, 2, 3 or 4");
    if (options.version == 4) {
        OnlineAdaptive online(capacity, seed, options);
        std::vector<Event> events;
        if (record_events) events.reserve(trace.size());
        for (const Page page : trace) {
            const auto event = online.access(page);
            if (record_events) events.push_back(event);
        }
        auto result = online.result();
        result.events = std::move(events);
        return result;
    }
    auto window = scaled_limit(capacity, options.window_factor);
    const bool aligned = options.version >= 2 && capacity > 20;
    // Small capacities retain V1's fast reaction. Larger caches need enough
    // time to measure the effects of eviction choices from the same starting state.
    if (aligned) {
        const auto maximum = std::numeric_limits<std::size_t>::max();
        window = window > maximum / 2 ? maximum : window * 2;
    }
    // Validate the supplied factor before halving it; invalid values must not
    // become valid simply because the caller selected a larger cache.
    scaled_limit(capacity, options.history_factor);
    const auto history_factor = options.version == 3 && capacity > 20
        ? std::max(std::size_t{1}, options.history_factor / 2) : options.history_factor;
    History history(scaled_limit(capacity, history_factor), options.version == 3);
    const auto check_interval = std::max(std::size_t{1}, window / 4);
    const auto margin = std::max(std::size_t{1}, window / (aligned ? 20 : 50));
    Cache actual(capacity, seed);
    // These are page-ID-only counterfactual simulations. On a policy switch,
    // actual physical frames are retained, never populated from shadow state.
    std::array<Cache, 3> shadows{Cache(capacity, seed), Cache(capacity, seed), Cache(capacity, seed)};
    std::deque<std::array<unsigned char, 3>> recent_losses;
    std::array<std::size_t, 3> losses{};
    std::size_t selected = capacity <= 20 ? 0 : 1;
    Result result;
    result.references = trace.size();
    if (record_events) result.events.reserve(trace.size());
    for (std::size_t i = 0; i < trace.size(); ++i) {
        // Selection uses only completed accesses, not the current outcome.
        if (recent_losses.size() == window && i % check_interval == 0) {
            std::size_t best = selected;
            for (std::size_t j = 0; j < losses.size(); ++j) {
                if (losses[j] < losses[best]) best = j;
            }
            if (losses[selected] - losses[best] > margin) {
                selected = best;
                ++result.policy_switches;
            }
        }
        if (aligned && i % window == 0) {
            // Copy only the actual page-ID/recency/RNG metadata into each
            // counterfactual cache, after the past-window decision. Never
            // copy a hypothetical resident into physical memory.
            for (auto& shadow : shadows) shadow = actual;
        }
        const auto event = actual.access(trace[i], i, static_cast<Policy>(selected), history);
        ++result.policy_uses[selected];
        if (event.hit) ++result.hits; else ++result.faults;
        if (event.evicted) ++result.evictions;
        if (record_events) result.events.push_back(event);
        std::array<unsigned char, 3> current{};
        for (std::size_t j = 0; j < shadows.size(); ++j) {
            current[j] = shadows[j].access(trace[i], i, static_cast<Policy>(j), history).hit ? 0 : 1;
            losses[j] += current[j];
        }
        recent_losses.push_back(current);
        if (recent_losses.size() > window) {
            for (std::size_t j = 0; j < losses.size(); ++j) losses[j] -= recent_losses.front()[j];
            recent_losses.pop_front();
        }
        history.observe(trace[i], i);
        result.history_peak = std::max(result.history_peak, history.size());
    }
    return result;
}
}  // namespace paging
