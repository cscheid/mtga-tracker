# Game States

A game state is announced by two messages: `GameStateType_Full` and `GameStateType_Diff`.

Game states appear to have sequential ids, but I don't know if the
messages arrive in sequence.  I'm assuming they do right now; if they
don't, it'll make my tracking harder.

Players have team ids and seat ids. Messages appear to refer to
players by both. I need to pay attention to this.

## other

What's the difference between a `priorityPlayer` and a `decisionPlayer`
in a `turnInfo` object?

Timestamp ticks appear to be in units of 10,000,000 ticks per second
(so 100 ns), counting the number of ticks from year 1 AD.

## todo

Main item left to do is for the thing to observe output.txt as output
is generated: presumably I can use [watchdog](https://pythonhosted.org/watchdog/)

