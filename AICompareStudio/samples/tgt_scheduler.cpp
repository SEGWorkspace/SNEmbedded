#include <vector>
#include <cstdint>
#include "Task.hpp"

namespace os {

class Scheduler {
public:
    void addTask(Task* t) { tasks_.push_back(t); }
    std::size_t taskCount() const { return tasks_.size(); }
private:
    std::vector<Task*> tasks_;
};

int tickPeriodMs() { return 5; }

void Scheduler_Run(Scheduler& s, uint32_t cycles, bool watchdog)
{
    for (uint32_t i = 0; i < cycles; ++i) {
        // run all tasks
        if (watchdog) { /* kick */ }
    }
}

} // namespace os
