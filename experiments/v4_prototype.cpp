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
constexpr std::size_t expert_count = 7;
constexpr std::size_t context_length = 12;
constexpr std::size_t anchor_candidates = 8;
constexpr std::size_t context_factor = 4;
constexpr bool reconcile = true;

std::size_t product(std::size_t a, std::size_t b) {
    const auto maximum = std::numeric_limits<std::size_t>::max();
    return a > maximum / b ? maximum : a * b;
}

std::size_t limit(std::size_t capacity, std::size_t factor) {
    if (capacity == 0) throw std::invalid_argument("frame count must be positive");
    if (factor == 0 || factor > 64) throw std::invalid_argument("adaptive factors must be in [1, 64]");
    return std::max(std::size_t{32}, product(capacity, factor));
}

// Shared observations, never a cache of page contents. Both the page records
// and the sequence of completed requests are bounded, independently of N.
class Observations {
    struct Conditional { Page predecessor; double gap; std::size_t last; };
    struct Record {
        std::size_t last;
        double gap = 0;
        double frequency = 1;
        bool repeated = false;
        std::list<Page>::iterator position;
        std::optional<Page> predecessor;
        std::vector<Conditional> conditions;
        double conditional_gap = 0;
        std::deque<std::size_t> gaps;
        double pattern_gap = 0;
    };
    const std::size_t history_limit_, tape_limit_, horizon_;
    const double decay_scale_;
    std::list<Page> order_;
    std::unordered_map<Page, Record> records_;
    std::deque<Page> tape_;
    std::size_t base_ = 0;
    std::unordered_map<Page, std::deque<std::size_t>> positions_;
    std::unordered_map<Page, std::size_t> forecast_;
    std::size_t forecast_span_ = 0;
public:
    Observations(std::size_t capacity, std::size_t history_factor)
        : history_limit_(limit(capacity, history_factor)),
          tape_limit_(std::max(std::size_t{256}, product(history_limit_, context_factor))),
          horizon_(std::max(std::size_t{32}, product(capacity, 4))),
          decay_scale_(static_cast<double>(std::max(std::size_t{32}, product(capacity, 8)))) {}

    std::size_t size() const { return records_.size(); }
    std::size_t tape_size() const { return tape_.size(); }
    bool predicts() const { return forecast_span_ != 0; }

    void prepare(Page page, std::size_t now) {
        forecast_.clear();
        forecast_span_ = 0;
        const auto found = positions_.find(page);
        if (found == positions_.end()) return;
        std::size_t anchor = 0, matched = 0, examined = 0;
        for (auto it = found->second.rbegin(); it != found->second.rend() && examined < anchor_candidates; ++it, ++examined) {
            const auto previous = *it;
            if (previous + 1 >= now) continue;
            std::size_t length = 1;
            while (length < context_length && previous >= base_ + length && now >= base_ + length &&
                   tape_[previous - length - base_] == tape_[now - length - base_]) ++length;
            if (length > matched) { anchor = previous; matched = length; }
            if (matched == context_length) break;
        }
        if (matched < 2) return;
        // Every copied reference is strictly before 'now'. The past suffix is
        // a forecast, not the actual future, and may be entirely wrong.
        forecast_span_ = std::min(horizon_, now - anchor - 1);
        for (std::size_t distance = 1; distance <= forecast_span_; ++distance) {
            forecast_.emplace(tape_[anchor + distance - base_], distance);
        }
    }

    double delay(Page page, std::size_t now) const {
        const auto found = records_.find(page);
        if (found == records_.end() || !found->second.repeated) return std::numeric_limits<double>::infinity();
        const auto& record = found->second;
        const double age = static_cast<double>(now - record.last);
        return age < record.gap ? record.gap - age : age;
    }

    double score(Page page, std::size_t now, std::size_t policy) const {
        if (policy == 5 || policy == 6) {
            const auto found = records_.find(page);
            if (found == records_.end() || !found->second.repeated) return std::numeric_limits<double>::infinity();
            const auto& record = found->second;
            const double age = static_cast<double>(now - record.last);
            const double estimate = policy == 5 ? record.conditional_gap : record.pattern_gap;
            return age < estimate ? estimate - age : age;
        }
        if (policy == 3 && forecast_span_) {
            const auto predicted = forecast_.find(page);
            if (predicted != forecast_.end()) return static_cast<double>(predicted->second);
            return static_cast<double>(forecast_span_) + delay(page, now);
        }
        if (policy == 4) {
            const auto found = records_.find(page);
            if (found == records_.end()) return std::numeric_limits<double>::infinity();
            const auto& record = found->second;
            // A log score avoids overflow when a formerly hot page goes cold.
            return static_cast<double>(now - record.last) / decay_scale_ - std::log2(record.frequency);
        }
        return delay(page, now);
    }

    void observe(Page page, std::size_t now) {
        const auto found = records_.find(page);
        if (found == records_.end()) {
            if (records_.size() == history_limit_) {
                records_.erase(order_.front());
                order_.pop_front();
            }
            order_.push_back(page);
            records_.emplace(page, Record{now, 0, 1, false, std::prev(order_.end()),
                                         tape_.empty() ? std::optional<Page>{} : tape_.back(), {}, 0, {}, 0});
        } else {
            auto& record = found->second;
            const double gap = static_cast<double>(now - record.last);
            record.gap = record.repeated ? 0.5 * record.gap + 0.5 * gap : gap;
            if (record.gaps.size() == 16) record.gaps.pop_front();
            record.gaps.push_back(now - record.last);
            record.pattern_gap = record.gap;
            std::size_t matched = 0;
            for (std::size_t j = record.gaps.size() - 1; j > 0;) {
                --j;
                if (record.gaps[j] != record.gaps.back()) continue;
                std::size_t length = 1;
                while (length < 4 && j >= length && record.gaps[j-length] == record.gaps[record.gaps.size()-1-length]) ++length;
                if (length > matched) { matched = length; record.pattern_gap = static_cast<double>(record.gaps[j+1]); }
                if (matched == 4) break;
            }
            if (record.predecessor) {
                auto condition = std::find_if(record.conditions.begin(), record.conditions.end(),
                    [&](const auto& c) { return c.predecessor == *record.predecessor; });
                if (condition != record.conditions.end()) { condition->gap = 0.5 * condition->gap + 0.5 * gap; condition->last = now; }
                else {
                    if (record.conditions.size() == 8) record.conditions.erase(std::min_element(record.conditions.begin(), record.conditions.end(),
                        [](const auto& a, const auto& b) { return a.last < b.last; }));
                    record.conditions.push_back({*record.predecessor, gap, now});
                }
            }
            record.conditional_gap = record.gap;
            if (!tape_.empty()) {
                record.predecessor = tape_.back();
                for (const auto& condition : record.conditions) {
                    if (condition.predecessor == *record.predecessor) record.conditional_gap = condition.gap;
                }
            }
            record.frequency = record.frequency * std::exp2(-gap / decay_scale_) + 1;
            record.last = now;
            record.repeated = true;
            order_.splice(order_.end(), order_, record.position);
        }
        if (tape_.size() == tape_limit_) {
            auto entry = positions_.find(tape_.front());
            entry->second.pop_front();
            if (entry->second.empty()) positions_.erase(entry);
            tape_.pop_front();
            ++base_;
        }
        tape_.push_back(page);
        positions_[page].push_back(now);
    }
};

class Cache {
    struct Entry { Page page; std::size_t last; };
    std::size_t capacity_;
    std::vector<Entry> frames_;
    std::unordered_map<Page, std::size_t> resident_;
    std::mt19937_64 random_;
    std::size_t random_slot(std::size_t count) {
        const auto bound = static_cast<std::uint64_t>(count);
        const auto threshold = (std::uint64_t{0} - bound) % bound;
        std::uint64_t draw;
        do { draw = random_(); } while (draw < threshold);
        return static_cast<std::size_t>(draw % bound);
    }
public:
    Cache(std::size_t capacity, std::uint64_t seed) : capacity_(capacity), random_(seed) {}
    bool contains(Page page) const { return resident_.count(page) != 0; }

    Event access(Page page, std::size_t now, std::size_t policy,
                 const Observations& observations, const Cache* target = nullptr) {
        const auto found = resident_.find(page);
        if (found != resident_.end()) {
            frames_[found->second].last = now;
            return {now + 1, page, true, found->second, {}};
        }
        std::size_t slot = frames_.size();
        std::optional<Page> evicted;
        if (frames_.size() < capacity_) {
            frames_.push_back({page, now});
        } else {
            // Follow a shadow by *evicting* an actual page it does not need.
            // Never copy in a shadow page. Since target already holds the
            // requested page, at least one eligible actual victim exists.
            std::vector<std::size_t> eligible;
            for (std::size_t j = 0; j < frames_.size(); ++j) {
                if (!target || !target->contains(frames_[j].page)) eligible.push_back(j);
            }
            if (eligible.empty()) throw std::logic_error("no legal reconciliation victim");
            slot = eligible[0];
            if (policy == 0) slot = eligible[random_slot(eligible.size())];
            else {
                double best = policy == 1 ? 0 : observations.score(frames_[slot].page, now, policy);
                for (const auto j : eligible) {
                    const double score = policy == 1 ? 0 : observations.score(frames_[j].page, now, policy);
                    if (score > best || (score == best && frames_[j].last < frames_[slot].last)) {
                        slot = j;
                        best = score;
                    }
                }
            }
            evicted = frames_[slot].page;
            resident_.erase(*evicted);
            frames_[slot] = {page, now};
        }
        resident_[page] = slot;
        return {now + 1, page, false, slot, evicted};
    }
};
} // namespace

struct OnlineAdaptive::Impl {
    const std::size_t window, check_interval, margin;
    Observations observations;
    Cache actual;
    std::array<Cache, expert_count> shadows;
    std::deque<std::array<unsigned char, expert_count>> recent;
    std::array<std::size_t, expert_count> losses{};
    std::size_t selected;
    Result statistics;

    Impl(std::size_t capacity, std::uint64_t seed, AdaptiveOptions options)
        : window(limit(capacity, options.window_factor)),
          check_interval(std::max(std::size_t{1}, window / 8)),
          margin(std::max(std::size_t{1}, window / 100)),
          observations(capacity, options.history_factor), actual(capacity, seed),
          shadows{Cache(capacity, seed), Cache(capacity, seed), Cache(capacity, seed),
                  Cache(capacity, seed), Cache(capacity, seed), Cache(capacity, seed), Cache(capacity, seed)}, selected(capacity <= 20 ? 0 : 1) {}

    Event access(Page page) {
        const auto now = statistics.references;
        if (recent.size() == window && now % check_interval == 0) {
            std::size_t best = selected;
            for (std::size_t j = 0; j < expert_count; ++j) if (losses[j] < losses[best]) best = j;
            if (losses[selected] - losses[best] > margin) { selected = best; ++statistics.policy_switches; }
        }
        observations.prepare(page, now);
        if (observations.predicts()) ++statistics.context_predictions;
        std::array<unsigned char, expert_count> current{};
        for (std::size_t j = 0; j < expert_count; ++j) {
            current[j] = shadows[j].access(page, now, j, observations).hit ? 0 : 1;
            losses[j] += current[j];
            statistics.expert_faults[j] += current[j];
        }
        const auto event = actual.access(page, now, selected, observations, reconcile ? &shadows[selected] : nullptr);
        ++statistics.references;
        ++statistics.expert_uses[selected];
        ++statistics.policy_uses[std::min(std::size_t{2}, selected)];
        if (event.hit) ++statistics.hits; else ++statistics.faults;
        if (event.evicted) ++statistics.evictions;
        recent.push_back(current);
        if (recent.size() > window) {
            for (std::size_t j = 0; j < expert_count; ++j) losses[j] -= recent.front()[j];
            recent.pop_front();
        }
        observations.observe(page, now);
        statistics.history_peak = std::max(statistics.history_peak, observations.size());
        statistics.context_history_peak = std::max(statistics.context_history_peak, observations.tape_size());
        return event;
    }
};

OnlineAdaptive::OnlineAdaptive(std::size_t capacity, std::uint64_t seed, AdaptiveOptions options)
    : impl_(std::make_unique<Impl>(capacity, seed, options)) {}
OnlineAdaptive::~OnlineAdaptive() = default;
OnlineAdaptive::OnlineAdaptive(OnlineAdaptive&&) noexcept = default;
OnlineAdaptive& OnlineAdaptive::operator=(OnlineAdaptive&&) noexcept = default;
Event OnlineAdaptive::access(Page page) { return impl_->access(page); }
const Result& OnlineAdaptive::result() const { return impl_->statistics; }
} // namespace paging
