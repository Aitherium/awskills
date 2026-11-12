# Lead with the next action — what the reader cannot see, they do not have
*Part II · Silence*

**Fires when:** anything an agent produces is read by a person: a reply, an end-of-task
report, an inbox of decision cards, a terminal home screen, a status line.

## The law

A screen that holds the answer but does not lead with it has not delivered it. The
reader's working memory is the screen. An item below the fold, a count with no remedy
beside it, or a 130-row inbox with no first step is the same failure as an alert that
never left the building (law 9): the information exists and nobody acts on it.

Four shapes, measured on one operator's own surfaces in a single morning:

| surface | what it showed | what was missing |
|---|---|---|
| decision inbox | "130 waiting", 24 failing jobs as 24 red rows each with two buttons | which one to do first |
| terminal home | an empty bordered pane with "ready" | anything to type |
| shell banner | "10 down" | the command that starts fixing it |
| status line | five alarms in red, wrapped past the width | which alarm matters |

The rule set that fixes it is small (adapted from *i-have-adhd*, MIT):

1. Line 1 is an action the reader can take now, computed from live data.
2. Multi-step work is numbered; one bounded action per step.
3. Each visible group holds at most five, ranked, then `+N more` — presentation only;
   nothing is dropped and the rest is one action away.
4. A count is always paired with its remedy.
5. The last line is one concrete next step.

## The check

- A render test feeds the surface a realistic overload (100+ items, several failures,
  a narrow width) and asserts: line 1 is an action, no group renders more than five,
  the remainder is reachable, nothing overflows the width.
- For prose, the first-and-last-line test: if the reader reads only those two lines,
  do they know what to do next and what just happened? An output style or report hook
  can enforce the closing line mechanically.
- The rule shapes what is SHOWN. A check that a cap did not shrink the underlying data
  (search results, stored items, analysis) belongs beside it — a cap that silently
  drops work is law 5's silence with a nicer layout.
