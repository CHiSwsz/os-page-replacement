// Standalone development driver, included after the V4 observation/cache types.
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

namespace paging {
struct Controller {
    std::string name;
    std::vector<std::size_t> pool;
    std::size_t window, interval, warmup;
    double margin;
    bool reconcile;
    Cache actual;
    std::array<double,expert_count> losses{};
    std::array<std::size_t,expert_count> uses{};
    std::size_t selected, faults=0, switches=0;
    Controller(std::string n,std::vector<std::size_t> p,std::size_t c,std::size_t w,
               std::size_t check,double m,std::size_t start,bool follow)
      :name(std::move(n)),pool(std::move(p)),window(w),interval(check),warmup(32),margin(m),
       reconcile(follow),actual(c,0),selected(start) {}
};
void sweep(const std::vector<Page>& trace,const std::string& filename,std::size_t capacity,
           std::size_t hf) {
    std::vector<std::vector<std::size_t>> pools={{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18},
      {0,1,2,3,5,6,7,10,12,13,14,15,18},{0,1,2,3,12,13,14,15},
      {1,2,12,13,14,15},{0,1,2,3,5,6,12,13,14,15}};
    if(expert_count>19) {
        for(std::size_t i=19;i<expert_count;++i) pools[0].push_back(i);
        pools.push_back({0,1,2,12,13,14,15,20,22,24});
        pools.push_back({1,2,12,13,14,15,20,22,24});
    }
    std::vector<Controller> controllers;
    for(std::size_t p=0;p<pools.size();++p) for(auto factor:{2U,4U,8U})
      for(auto margin:{1U,20U,100U}) for(auto start:{2U,15U}) {
        const auto w=std::max(std::size_t{32},capacity*factor);
        std::ostringstream name; name<<"p"<<p<<"w"<<factor<<"m"<<margin<<"s"<<start;
        controllers.emplace_back(name.str(),pools[p],capacity,w,std::max(std::size_t{1},w/8),
          margin==1?1.0:std::max(1.0,static_cast<double>(w)/margin),start,true);
    }
    Observations observations(capacity,capacity>20?std::max(std::size_t{1},hf/2):hf);
    std::vector<Cache> shadows;
    for(std::size_t i=0;i<expert_count;++i) shadows.emplace_back(capacity,0);
    std::array<std::size_t,expert_count> faults{};
    for(std::size_t now=0;now<trace.size();++now) {
        for(auto& c:controllers) if(now>=c.warmup && now%c.interval==0) {
            auto best=c.selected;
            for(auto i:c.pool) if(c.losses[i]<c.losses[best]) best=i;
            if(c.losses[c.selected]-c.losses[best]>c.margin) { c.selected=best; ++c.switches; }
        }
        observations.prepare(trace[now],now);
        for(std::size_t i=0;i<expert_count;++i) {
            const bool miss=!shadows[i].access(trace[now],now,i,observations).hit;
            faults[i]+=miss;
            for(auto& c:controllers) c.losses[i]=c.losses[i]*(1.0-1.0/c.window)+miss;
        }
        for(auto& c:controllers) {
            c.faults+=!c.actual.access(trace[now],now,c.selected,observations,
                                       c.reconcile?&shadows[c.selected]:nullptr).hit;
            ++c.uses[c.selected];
        }
        observations.observe(trace[now],now);
    }
    for(const auto& c:controllers) {
        std::cout<<c.name<<','<<filename<<','<<capacity<<','<<c.faults<<','<<c.switches;
        for(auto n:faults) std::cout<<','<<n;
        for(auto n:c.uses) std::cout<<','<<n;
        std::cout<<'\n';
    }
}
void experiment(const std::vector<Page>& trace,const std::string& filename,
                std::size_t capacity,const std::vector<std::size_t>& pool,
                std::size_t wf,std::size_t hf,const std::string& mode) {
    const auto window=2*std::max(std::size_t{32},wf*capacity);
    Observations observations(capacity,capacity>20?std::max(std::size_t{1},hf/2):hf);
    Cache actual(capacity,0);
    std::vector<Cache> shadows;
    for(std::size_t i=0;i<expert_count;++i) shadows.emplace_back(capacity,0);
    std::array<double,expert_count> losses{};
    std::array<std::size_t,expert_count> faults{}, uses{};
    std::size_t selected=capacity<=20?2:1, actual_faults=0, switches=0;
    if(std::find(pool.begin(),pool.end(),selected)==pool.end()) selected=pool.front();
    for(std::size_t now=0;now<trace.size();++now) {
        if(now>=window && now%(window/4)==0) {
            auto best=selected;
            for(auto i:pool) if(losses[i]<losses[best]) best=i;
            if(losses[selected]-losses[best]>std::max(1.0,window/20.0)) { selected=best; ++switches; }
        }
        observations.prepare(trace[now],now);
        for(std::size_t i=0;i<expert_count;++i) {
            const bool miss=!shadows[i].access(trace[now],now,i,observations).hit;
            faults[i]+=miss;
            losses[i]=losses[i]*(1.0-1.0/window)+miss;
        }
        actual_faults+=!actual.access(trace[now],now,selected,observations,
                                     mode=="direct"?nullptr:&shadows[selected]).hit;
        ++uses[selected];
        observations.observe(trace[now],now);
    }
    std::cout<<filename<<','<<capacity<<','<<actual_faults<<','<<switches;
    for(auto n:faults) std::cout<<','<<n;
    for(auto n:uses) std::cout<<','<<n;
    std::cout<<'\n';
}
}

int main(int argc,char** argv) {
    if(argc<6) { std::cerr<<"usage: predictor POOL W H follow|direct FILE...\n"; return 2; }
    const bool sweeping=std::string(argv[1])=="sweep";
    std::vector<std::size_t> pool;
    std::stringstream p(argv[1]); std::string value;
    while(!sweeping && std::getline(p,value,',')) {
        auto index=std::stoull(value);
        if(index>=paging::expert_count) return 2;
        pool.push_back(index);
    }
    if(sweeping) std::cout<<"variant,";
    std::cout<<"dataset,frames,faults,switches";
    for(std::size_t i=0;i<paging::expert_count;++i) std::cout<<",expert_faults_"<<i;
    for(std::size_t i=0;i<paging::expert_count;++i) std::cout<<",expert_uses_"<<i;
    std::cout<<'\n';
    for(int a=5;a<argc;++a) {
        std::ifstream in(argv[a]); if(!in) return 2;
        std::vector<paging::Page> trace; std::string line;
        while(std::getline(in,line)) if(!line.empty()) trace.push_back(std::stoull(line,nullptr,16));
        for(auto f:{5U,10U,20U,50U,100U}) {
            if(sweeping) paging::sweep(trace,argv[a],f,std::stoull(argv[3]));
            else paging::experiment(trace,argv[a],f,pool,std::stoull(argv[2]),std::stoull(argv[3]),argv[4]);
        }
    }
}
