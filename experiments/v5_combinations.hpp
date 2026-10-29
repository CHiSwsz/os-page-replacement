// Development comparison: weighted membership voting versus legal shadow following.
#include <fstream>
#include <iostream>
#include <sstream>
namespace paging { namespace {
struct Mixer {
    std::string name;
    std::vector<std::size_t> pool;
    std::vector<Page> pages;
    std::vector<std::size_t> last;
    std::unordered_map<Page,std::size_t> resident;
    std::array<double,expert_count> losses{},weights{};
    std::array<std::size_t,expert_count> uses{};
    std::size_t capacity,window,selected,faults=0,switches=0;
    double temperature;
    bool vote;
    Mixer(std::string n,std::vector<std::size_t> p,std::size_t c,std::size_t w,
          double t,std::size_t start,bool v):name(n),pool(p),capacity(c),window(w),selected(start),temperature(t),vote(v) {}
    void access(Page page,std::size_t now,const Observations& obs,const std::vector<Cache>& shadows) {
        if(now>=32 && now%std::max(std::size_t{1},window/8)==0) {
            auto best=selected;
            for(auto e:pool) if(losses[e]<losses[best]) best=e;
            if(losses[selected]-losses[best]>std::max(1.0,window/20.0)) { selected=best; ++switches; }
        }
        ++uses[selected];
        auto found=resident.find(page);
        if(found!=resident.end()) { last[found->second]=now; return; }
        ++faults;
        if(pages.size()<capacity) {
            resident.emplace(page,pages.size()); pages.push_back(page); last.push_back(now); return;
        }
        double minimum=infinity;
        for(auto e:pool) minimum=std::min(minimum,losses[e]);
        for(auto e:pool) weights[e]=std::exp(-(losses[e]-minimum)/temperature);
        auto score=[&](std::size_t i) {
            if(!vote) return shadows[selected].contains(pages[i]) ? 1.0:0.0;
            double s=0; for(auto e:pool) if(shadows[e].contains(pages[i])) s+=weights[e]; return s;
        };
        std::size_t victim=0;
        auto retention=score(0), prediction=obs.score(pages[0],now,selected);
        for(std::size_t i=1;i<pages.size();++i) {
            const auto s=score(i), predicted=obs.score(pages[i],now,selected);
            const bool tie=s==retention;
            const bool lru=selected<=1;
            if(s<retention || (tie && ((!lru && predicted>prediction) ||
               ((lru || predicted==prediction) && last[i]<last[victim])))) {
                victim=i; retention=s; prediction=predicted;
            }
        }
        resident.erase(pages[victim]); pages[victim]=page; last[victim]=now; resident.emplace(page,victim);
    }
    static constexpr double infinity=std::numeric_limits<double>::infinity();
};
void combine(const std::vector<Page>& trace,const std::string& file,std::size_t capacity) {
    std::vector<std::vector<std::size_t>> pools;
    std::vector<std::size_t> all;
    for(std::size_t e=0;e<expert_count;++e) all.push_back(e);
    pools.push_back(all);
    pools.push_back({1,2,12,13,14,15});
    pools.push_back({1,2,12,13,14,15,22});
    pools.push_back({0,1,2,3,5,6,12,13,14,15,22});
    pools.push_back({1,2,3,5,6,12,13,14,15,20,22,24});
    pools.push_back({0,1,2,3,5,6,7,10,12,13,14,15,18,20,22,24});
    std::vector<Mixer> mixers;
    for(std::size_t p=0;p<pools.size();++p) for(auto f:{4U,8U,16U}) {
        const auto w=std::max(std::size_t{32},capacity*f);
        for(auto start:{2U,15U}) {
            std::ostringstream n; n<<"follow_p"<<p<<"w"<<f<<"s"<<start;
            mixers.emplace_back(n.str(),pools[p],capacity,w,1.0,start,false);
        }
        for(double t:{1.0,4.0,16.0}) {
            std::ostringstream n; n<<"vote_p"<<p<<"w"<<f<<"t"<<t;
            mixers.emplace_back(n.str(),pools[p],capacity,w,t,15,true);
        }
    }
    Observations obs(capacity,capacity>20?8:16);
    std::vector<Cache> shadows; for(std::size_t e=0;e<expert_count;++e) shadows.emplace_back(capacity,0);
    std::array<std::size_t,expert_count> faults{};
    for(std::size_t now=0;now<trace.size();++now) {
        obs.prepare(trace[now],now);
        std::array<bool,expert_count> misses{};
        for(std::size_t e=0;e<expert_count;++e) { misses[e]=!shadows[e].access(trace[now],now,e,obs).hit; faults[e]+=misses[e]; }
        for(auto& m:mixers) {
            m.access(trace[now],now,obs,shadows);
            for(auto e:m.pool) m.losses[e]=m.losses[e]*(1.0-1.0/m.window)+misses[e];
        }
        obs.observe(trace[now],now);
    }
    for(const auto& m:mixers) {
        std::cout<<m.name<<','<<file<<','<<capacity<<','<<m.faults<<','<<m.switches;
        for(auto n:faults) std::cout<<','<<n;
        for(auto n:m.uses) std::cout<<','<<n;
        std::cout<<'\n';
    }
}
} }
int main(int argc,char** argv) {
    std::cout<<"variant,dataset,frames,faults,switches";
    for(std::size_t i=0;i<paging::expert_count;++i) std::cout<<",expert_faults_"<<i;
    for(std::size_t i=0;i<paging::expert_count;++i) std::cout<<",expert_uses_"<<i;
    std::cout<<'\n';
    for(int i=1;i<argc;++i) {
        std::ifstream in(argv[i]); if(!in) return 2;
        std::vector<paging::Page> trace; std::string line;
        while(std::getline(in,line)) if(!line.empty()) trace.push_back(std::stoull(line,nullptr,16));
        for(auto f:{5U,10U,20U,50U,100U}) paging::combine(trace,argv[i],f);
    }
}
