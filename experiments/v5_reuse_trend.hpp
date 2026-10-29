// Development prototype: bounded delayed-label reuse predictors inspired by
// LRB (NSDI 2020) and LIRS2 (2021). This is not a reproduction of either paper.
// Labels are added only after the corresponding page returns or its history
// record expires. Never receives a trace array or a future-reference index.
#pragma once
#include <array>
#include <cstdint>
#include <deque>
#include <limits>
#include <list>
#include <unordered_map>
#include <cmath>
#include <algorithm>
#include <vector>

namespace paging {
class ReuseModel {
    static constexpr std::size_t sample_count = 16;
    static constexpr double infinity = std::numeric_limits<double>::infinity();
    struct Key {
        std::uint64_t a=0, b=0, c=0;
        unsigned kind=0;
        bool operator==(const Key& x) const { return a==x.a && b==x.b && c==x.c && kind==x.kind; }
    };
    struct Hash {
        std::size_t operator()(const Key& k) const {
            return std::hash<std::uint64_t>{}(k.a) ^ (k.b*0x9e3779b97f4a7c15ULL) ^
                   (k.c*0x517cc1b727220a95ULL) ^ (k.kind*0x94d049bb133111ebULL);
        }
    };
    struct Model {
        std::array<double,sample_count> samples{};
        std::size_t size=0, cursor=0;
        double ewma=0;
        std::vector<std::pair<double,double>> clusters;
        double censored=0;
        std::list<Key>::iterator position;
    };
    struct Record {
        std::size_t last=0, gap=0, previous=0, count=1;
        std::array<Key,8> keys{};
        Page previous_page=0;
        bool successor_known=false;
        std::array<std::size_t,8> gaps{};
        std::size_t used=0;
        std::list<Page>::iterator position;
    };
    std::size_t history_limit_, model_limit_, horizon_;
    std::list<Page> order_;
    std::unordered_map<Page,Record> records_;
    std::list<Key> model_order_;
    std::unordered_map<Key,Model,Hash> models_;
    Page predecessor_=0;
    Page second_predecessor_=0;
    bool have_predecessor_=false;

    static std::size_t bucket(std::size_t gap) {
        if (gap<16) return gap;
        unsigned exponent=0;
        std::size_t n=gap;
        while (n>=16) { n >>= 1; ++exponent; }
        return 16 + (exponent-1)*8 + (n-8);
    }
    void train(const Key& key,double label) {
        auto found=models_.find(key);
        if(found==models_.end()) {
            if(models_.size()==model_limit_) {
                models_.erase(model_order_.front()); model_order_.pop_front();
            }
            model_order_.push_back(key);
            Model model; model.position=std::prev(model_order_.end());
            found=models_.emplace(key,model).first;
        } else model_order_.splice(model_order_.end(),model_order_,found->second.position);
        auto& m=found->second;
        for(auto& point:m.clusters) point.second*=.98;
        m.censored*=.98;
        if(!std::isfinite(label)) ++m.censored;
        else {
            bool matched=false;
            for(auto& point:m.clusters) if(point.first==label) { ++point.second; matched=true; break; }
            if(!matched) {
                m.clusters.emplace_back(label,1.0);
                std::sort(m.clusters.begin(),m.clusters.end());
                if(m.clusters.size()>sample_count) {
                    std::size_t nearest=0; double distance=infinity;
                    for(std::size_t j=0;j+1<m.clusters.size();++j) {
                        const auto left=m.clusters[j].first, right=m.clusters[j+1].first;
                        const double delta=(right-left)/(right+left);
                        if(delta<distance) { distance=delta; nearest=j; }
                    }
                    auto& a=m.clusters[nearest]; const auto b=m.clusters[nearest+1];
                    a.first=(a.first*a.second+b.first*b.second)/(a.second+b.second);
                    a.second+=b.second;
                    m.clusters.erase(m.clusters.begin()+static_cast<std::ptrdiff_t>(nearest+1));
                }
            }
        }
        m.samples[m.cursor]=label;
        m.cursor=(m.cursor+1)%sample_count;
        m.size=std::min(sample_count,m.size+1);
        if(std::isfinite(label)) m.ewma=m.ewma ? .5*m.ewma+.5*label : label;
    }
    double estimate(const Key& key,double age,bool conditional) const {
        const auto it=models_.find(key);
        if(it==models_.end() || it->second.size<2) return infinity;
        const auto& m=it->second;
        if(!conditional) {
            if(!m.ewma) return infinity;
            return age<m.ewma ? m.ewma-age : age;
        }
        double cost=m.censored*std::max(1.0,static_cast<double>(horizon_)-age), hits=0;
        for(const auto& point:m.clusters) if(point.first>age) {
            cost+=(point.first-age)*point.second; hits+=point.second;
        }
        return hits ? cost/hits : infinity;
    }
    double fallback(const Record& r,double age) const {
        if(!r.gap) return infinity;
        return age<r.gap ? r.gap-age : age;
    }
public:
    ReuseModel(std::size_t capacity,std::size_t factor)
      :history_limit_(std::max(std::size_t{32},capacity*factor)),
       model_limit_(history_limit_*16),horizon_(std::max(std::size_t{64},capacity*32)) {}

    void prepare(Page page,std::size_t now) {
        if(!have_predecessor_) return;
        auto it=records_.find(predecessor_);
        if(it==records_.end() || it->second.last+1!=now) return;
        auto& r=it->second;
        r.successor_known=true;
        r.keys[6]=Key{page,bucket(r.gap),0,6};
        r.keys[7]=Key{r.previous_page,page,bucket(r.gap),7};
    }

    double score(Page page,std::size_t now,std::size_t policy) const {
        auto it=records_.find(page);
        if(it==records_.end()) return infinity;
        const auto& r=it->second;
        const double age=static_cast<double>(now-r.last);
        if(policy>=18) {
            if(!r.gap) return infinity;
            const double gap=static_cast<double>(r.gap), previous=static_cast<double>(r.previous);
            double prediction=gap;
            if(policy==18 || policy==19 || policy==25) {
                if(r.previous) prediction=2*gap-previous;
                if(policy!=19) prediction=std::max(.5*gap,std::min(2*gap,prediction));
            } else if(policy==20 || policy==26) {
                if(r.used>=4) prediction=std::max(.5*previous,std::min(2*previous,2*previous-r.gaps[3]));
                else if(r.previous) prediction=previous;
            } else if(policy==21 && r.used>=6) {
                double one=0,two=0;
                for(std::size_t i=0;i+2<r.used;++i) one+=std::abs(static_cast<double>(r.gaps[i])-2.0*r.gaps[i+1]+r.gaps[i+2]);
                for(std::size_t i=0;i+4<r.used;++i) two+=std::abs(static_cast<double>(r.gaps[i])-2.0*r.gaps[i+2]+r.gaps[i+4]);
                const auto period=two/(r.used-4)<.75*one/(r.used-2)?2U:1U;
                const double base=r.gaps[period-1];
                prediction=std::max(.5*base,std::min(2*base,2*base-r.gaps[2*period-1]));
            } else if(policy==22 && r.previous) prediction=std::max(.5*gap,std::min(2*gap,gap*gap/previous));
            else if(policy==23 && r.previous) prediction=std::min(gap,previous);
            prediction=std::max(1.0,prediction);
            return age<prediction ? prediction-age : (policy>=24?infinity:age);
        }
        if(policy>=12) {
            const auto key=5+(policy-12)/2;
            if(key>=6 && !r.successor_known) return fallback(r,age);
            auto m=models_.find(r.keys[key]);
            if(m==models_.end() || m->second.size<4) return fallback(r,age);
            const auto prediction=estimate(r.keys[key],age,policy%2==1);
            return policy%2==1 || std::isfinite(prediction) ? prediction : fallback(r,age);
        }
        if(policy<5) {
            const auto value=estimate(r.keys[policy],age,false);
            return std::isfinite(value)?value:fallback(r,age);
        }
        if(policy<8) {
            const unsigned key=static_cast<unsigned>(policy-4);
            const auto it_model=models_.find(r.keys[key]);
            if(it_model==models_.end() || it_model->second.size<4) return fallback(r,age);
            return estimate(r.keys[key],age,true);
        }
        if(policy==8) return fallback(r,age);
        if(policy==9) {
            const auto value=r.previous ? r.previous : r.gap;
            return !value ? infinity : age<value ? value-age : age;
        }
        if(policy==10) return r.gap ? age+r.gap : infinity;
        // Search only this page's already completed gap sequence for a prior
        // occurrence of the current gap suffix, then replay its observed next gap.
        std::size_t prediction=0, best=0;
        for(std::size_t anchor=1;anchor<r.used;++anchor) {
            std::size_t matched=0;
            while(anchor+matched<r.used && r.gaps[matched]==r.gaps[anchor+matched]) ++matched;
            if(matched>best) { best=matched; prediction=r.gaps[anchor-1]; }
        }
        if(!best) return fallback(r,age);
        return age<prediction ? prediction-age : age;
    }

    void observe(Page page,std::size_t now) {
        auto it=records_.find(page);
        if(it==records_.end()) {
            if(records_.size()==history_limit_) {
                const auto old=records_.find(order_.front());
                for(std::size_t k=0;k<(old->second.successor_known?8:6);++k) train(old->second.keys[k],infinity);
                records_.erase(old); order_.pop_front();
            }
            order_.push_back(page);
            Record r; r.last=now; r.position=std::prev(order_.end());
            it=records_.emplace(page,r).first;
        } else {
            auto& r=it->second;
            const auto gap=now-r.last;
            for(std::size_t k=0;k<(r.successor_known?8:6);++k) train(r.keys[k],static_cast<double>(gap));
            r.previous=r.gap; r.gap=gap; r.last=now; ++r.count;
            for(std::size_t j=r.gaps.size()-1;j>0;--j) r.gaps[j]=r.gaps[j-1];
            r.gaps[0]=gap; r.used=std::min(r.used+1,r.gaps.size());
            order_.splice(order_.end(),order_,r.position);
        }
        auto& r=it->second;
        const auto gap=bucket(r.gap), prior=bucket(r.previous);
        r.keys[0]=Key{page,gap,0,0};
        r.keys[1]=Key{gap,0,0,1};
        r.keys[2]=Key{gap,prior,0,2};
        r.keys[3]=Key{have_predecessor_?predecessor_:page,gap,0,3};
        r.keys[4]=Key{gap,prior,std::min(std::size_t{4},r.count),4};
        r.keys[5]=Key{predecessor_,second_predecessor_,gap,5};
        r.previous_page=predecessor_; r.successor_known=false;
        second_predecessor_=predecessor_; predecessor_=page; have_predecessor_=true;
    }
};
} // namespace paging
