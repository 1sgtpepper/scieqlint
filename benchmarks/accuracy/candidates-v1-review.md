# Proposed source-backed accuracy cases

These 100 candidates are pending human review. They execute separately from
`corpus-v1.json` and do not contribute to stable-release evidence. The approved
count remains 2/100. Passing these proposed expectations in CI does not approve
their labels or establish real-world precision/recall.

The set contains 37 algebra comparisons (15 identities and 22 non-identities),
48 dimensional checks (47 homogeneous and one incompatible sum), and 15
unsupported-notation cases. Each original equation appears once, in a supplied
LaTeX, Markdown or notebook wrapper (34/33/33). All original sources are TeX;
these wrappers do not claim naturally occurring Markdown or notebook coverage.

## What the expectations mean

- `ALG001` asks whether a universal scalar identity holds. A conditional
  textbook exercise can correctly fail that test without being a source error.
  Exact expansion gives each residual below; every nonzero residual has an
  explicit counterexample. No equation is accepted merely because its sides
  contain different variable sets and the checker remains quiet.
- Dimensional cases use the quantity meanings and declared dimensions below.
  Homogeneity does not prove a physical law, numerical coefficient, sign,
  approximation, temperature origin or derivative. Algebra error reporting is
  disabled for these cases; parser skip diagnostics remain active.
- `PARSE020` and `PARSE021` assert a documented informational skip. The
  corresponding formulas receive no mathematical truth judgment.
- Labels are proposed from exact arithmetic, dimensional exponent arithmetic
  and the documented grammar independently of analyzer execution. They are not captured
  analyzer output and have not been approved by a human reviewer.

The frozen collection contains 500 structurally distinct expressions, not 500
independent scientific laws. Related forms remain grouped by the family names
below. Numerical substitutions, renamed variables and format wrappers must not
be counted as new independent equations. All 139 equations from Dickson's book
are reserved outside this initial execution set for future evaluation. That is
a source reservation, not a claim of family-disjoint or blind evaluation;
overlap with algebra families must be adjudicated before reporting a score.

## Sources and notation

`LicenseRef-Public-Domain-US` records the source catalogs' public-domain-in-USA
status; it is not a Creative Commons license or a worldwide rights assertion.
Only the mathematical expressions are included here. Original edition notices
remain in the linked source files. Each source is UTF-8, retrieved 2026-09-06.

| Source | Cases | Pinned source SHA-256 |
|---|---:|---|
| [Wallace C. Boyden — A First Book in Algebra](https://www.gutenberg.org/ebooks/13309); [TeX](https://www.gutenberg.org/files/13309/13309-t/13309-t.tex) | 33 | `c682388e0d83aac3e2dc79e86e04db793c34c2441b4d74bb6c35a01c63432d76` |
| [Leonard E. Dickson — First Course in the Theory of Equations](https://www.gutenberg.org/ebooks/29785); [TeX](https://www.gutenberg.org/files/29785/29785-t/29785-t.tex) | 0 | `9f41486652b5a75139383db46d8b292783f3d888dc03396144d182dcbd3f21dc` |
| [Silvanus P. Thompson — Calculus Made Easy](https://www.gutenberg.org/ebooks/33283); [TeX](https://www.gutenberg.org/files/33283/33283-t/33283-t.tex) | 21 | `fb6a9195621aeba3302d2359af4ff7cd74b285d9fb57c16431c21c0b85ed5776` |
| [Max Planck; translated by Alexander Ogg — Treatise on Thermodynamics](https://www.gutenberg.org/ebooks/50880); [TeX](https://www.gutenberg.org/files/50880/50880-t/50880-t.tex) | 46 | `4f79b464f82555ddebb02aea86097e372cd530ff67c8ca7ca6ea4f8776a0ad3f` |

Source line numbers below refer to those pinned TeX files. Original expressions
are shown with line breaks collapsed for display; the proposed test expression
is shown separately. Scalar transcriptions make multiplication explicit, replace
fraction layout by `/`, flatten static subscripts, spell Greek symbols in ASCII
and preserve prime-indexed quantities with `p`/`pp`/`ppp` suffixes. `dX` names a
differential quantity with X's dimensions; it does not add calculus support.
Four dimensional cases clear sums in denominators to stay inside the current
scalar grammar. Their original nonzero-domain restrictions and exact
equivalence certificates are retained below. These test the rearranged
expressions, not support for the original denominator syntax.
Tag macros, trailing sentence punctuation and line wrapping are presentation
only. Unsupported cases preserve the substantive notation that causes a skip.
Review the transcription and its assumptions as well as the proposed codes.

Dimension certificates use exponent order `(M, L, T, Theta)`. All variables
and denominator restrictions are case-local. In particular, Planck's uppercase
T can mean pressure times specific volume, L can mean latent heat, and h can
mean specific heat. These are not assigned dimensions by their names.

## Candidate review

### boyden-algebra-eac710922068

Source lines 1839–1839; family `signed-grouping`; human review **pending**.

- Original: `a + (b - c - x) = a + b - c - x`
- Test: `a+(b-c-x)=a+b-c-x`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-46163c57dfa7

Source lines 3314–3314; family `factoring`; human review **pending**.

- Original: `2am+2ax+bm+bx=2a(m+x)+b(m+x).`
- Test: `2*a*m+2*a*x+b*m+b*x=2*a*(m+x)+b*(m+x)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-bb2652b6cbea

Source lines 4342–4343; family `rational-cancellation`; human review **pending**.

- Original: `\frac{5a^2b \div 5ab}{10ab^2 \div 5ab} = \frac{a}{2b}`
- Test: `((5*a^2*b)/(5*a*b))/((10*a*b^2)/(5*a*b))=a/(2*b)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. Assume 2*b != 0; 5*a*b != 0.
- Exact `left - right`: `0`.

### boyden-algebra-17f167238d27

Source lines 1841–1841; family `signed-grouping`; human review **pending**.

- Original: `a + c - d + e = a + (c - d + e)`
- Test: `a+c-d+e=a+(c-d+e)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-6b1a20d51f8f

Source lines 3331–3331; family `factoring`; human review **pending**.

- Original: `a^8+a^6-a^5-a^3+a^2+1=a^6(a^2+1)-a^3(a^2+1)+(a^2+1).`
- Test: `a^8+a^6-a^5-a^3+a^2+1=a^6*(a^2+1)-a^3*(a^2+1)+(a^2+1)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-ed91d866058d

Source lines 4402–4403; family `rational-cancellation`; human review **pending**.

- Original: `\frac{ac-bc-d}{c} = a - b -\frac{d}{c}`
- Test: `(a*c-b*c-d)/c=a-b-d/c`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. Assume c != 0.
- Exact `left - right`: `0`.

### boyden-algebra-d23e379903b0

Source lines 1855–1855; family `signed-grouping`; human review **pending**.

- Original: `x - (y + z - c) = x - y - z + c`
- Test: `x-(y+z-c)=x-y-z+c`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-5b370b2a0d9d

Source lines 2273–2273; family `monomial-powers`; human review **pending**.

- Original: `(5 a^2 b^3)^2 = 25 a^4 b^6`
- Test: `(5*a^2*b^3)^2=25*a^4*b^6`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-9d6952962b13

Source lines 2274–2274; family `monomial-powers`; human review **pending**.

- Original: `(3 x y^2 z)^3 = 27 x^3 y^6 z^3`
- Test: `(3*x*y^2*z)^3=27*x^3*y^6*z^3`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-f3d96f99cd4d

Source lines 2517–2517; family `rational-cancellation`; human review **pending**.

- Original: `6a^4 b^4 c^6 \div 2a^3 b^2 c^3 = 3a b^2 c^3`
- Test: `(6*a^4*b^4*c^6)/(2*a^3*b^2*c^3)=3*a*b^2*c^3`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. Assume 2*a**3*b**2*c**3 != 0.
- Exact `left - right`: `0`.

### boyden-algebra-81c8eb19f02a

Source lines 5783–5783; family `factoring`; human review **pending**.

- Original: `\left(a^2+ab+b^2\right)^2-\left(a^2-ab+b^2\right)^2=4ab(a^2+b^2)`
- Test: `(a^2+a*b+b^2)^2-(a^2-a*b+b^2)^2=4*a*b*(a^2+b^2)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### thompson-calculus-347940d55a04

Source lines 3021–3021; family `numeric-ratios`; human review **pending**.

- Original: `\frac{200}{4} = \frac{50}{1}`
- Test: `200/4=50/1`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. Assume 4 != 0; 1 != 0.
- Exact `left - right`: `0`.

### planck-thermodynamics-3f5ae3dd6195

Source lines 8879–8880; family `phase-rule-counting`; human review **pending**.

- Original: `\bigl[(\alpha - 1)\beta + 2\bigr] - \bigl[\alpha (\beta - 1)\bigr] = \alpha - \beta + 2`
- Test: `((alpha-1)*beta+2)-(alpha*(beta-1))=alpha-beta+2`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `0`.

### boyden-algebra-95df0b53cc95

Source lines 5438–5438; family `linear-equations`; human review **pending**.

- Original: `27 + 10x = 13x + 23`
- Test: `27+10*x=13*x+23`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `4 - 3*x`.
- Counterexample: `x=1` gives left `37` and right `36`.

### boyden-algebra-a80c67d3233f

Source lines 5523–5523; family `linear-equations`; human review **pending**.

- Original: `5x-4=10x+ 11`
- Test: `5*x-4=10*x+11`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-5*x - 15`.
- Counterexample: `x=1` gives left `1` and right `21`.

### boyden-algebra-e33e63b4e4e1

Source lines 5528–5528; family `linear-equations`; human review **pending**.

- Original: `9x-(2x-5)=4x+(13 + x)`
- Test: `9*x-(2*x-5)=4*x+(13+x)`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `2*x - 8`.
- Counterexample: `x=1` gives left `12` and right `18`.

### boyden-algebra-323315f39c0e

Source lines 5530–5530; family `linear-equations`; human review **pending**.

- Original: `12x-18x+17=8x+3`
- Test: `12*x-18*x+17=8*x+3`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `14 - 14*x`.
- Counterexample: `x=2` gives left `5` and right `19`.

### boyden-algebra-c8da5ef690a8

Source lines 5532–5532; family `linear-equations`; human review **pending**.

- Original: `5x-27-11x+16=98-40x-41`
- Test: `5*x-27-11*x+16=98-40*x-41`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `34*x - 68`.
- Counterexample: `x=1` gives left `-17` and right `17`.

### boyden-algebra-f4b614224291

Source lines 5537–5537; family `quadratic-equations`; human review **pending**.

- Original: `(x+4)(x+7)=(x+2)(x+11)`
- Test: `(x+4)*(x+7)=(x+2)*(x+11)`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `6 - 2*x`.
- Counterexample: `x=1` gives left `40` and right `36`.

### boyden-algebra-8c67e8ee4da2

Source lines 5538–5538; family `cubic-equations`; human review **pending**.

- Original: `(x-1)(x+4)(x-2)=x(x-2)(x+2)`
- Test: `(x-1)*(x+4)*(x-2)=x*(x-2)*(x+2)`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `x**2 - 6*x + 8`.
- Counterexample: `x=1` gives left `0` and right `-3`.

### boyden-algebra-731e321f476b

Source lines 5542–5542; family `quadratic-equations`; human review **pending**.

- Original: `(x+1)^{2}+(x-5)^{2}=2(x+5)^{2}`
- Test: `(x+1)^2+(x-5)^2=2*(x+5)^2`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-28*x - 24`.
- Counterexample: `x=1` gives left `20` and right `72`.

### boyden-algebra-b1da1f903c38

Source lines 5544–5544; family `linear-equations`; human review **pending**.

- Original: `7x - 15 + 4x - 6 = 4x - 9 - 9x`
- Test: `7*x-15+4*x-6=4*x-9-9*x`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `16*x - 12`.
- Counterexample: `x=1` gives left `-10` and right `-14`.

### boyden-algebra-e864b5a765cb

Source lines 5624–5624; family `parameter-equations`; human review **pending**.

- Original: `b(2x-a)-a^2 = 2x(a+b)-3ab`
- Test: `b*(2*x-a)-a^2=2*x*(a+b)-3*a*b`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-a**2 + 2*a*b - 2*a*x`.
- Counterexample: `a=1, b=1, x=1` gives left `0` and right `1`.

### boyden-algebra-fd6be419b186

Source lines 5629–5629; family `parameter-equations`; human review **pending**.

- Original: `b^4-x^2+2bx=(b^2+x)(b^2-x)`
- Test: `b^4-x^2+2*b*x=(b^2+x)*(b^2-x)`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `2*b*x`.
- Counterexample: `b=1, x=1` gives left `2` and right `0`.

### boyden-algebra-a98e964dc0f8

Source lines 5631–5631; family `parameter-equations`; human review **pending**.

- Original: `x^2+4a^2+a^4=\left(x+a^2\right)^2`
- Test: `x^2+4*a^2+a^4=(x+a^2)^2`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-2*a**2*x + 4*a**2`.
- Counterexample: `a=1, x=1` gives left `6` and right `4`.

### boyden-algebra-22c07cbe35a6

Source lines 5633–5633; family `parameter-equations`; human review **pending**.

- Original: `b^2(x-b)+a^2(x-a)=abx`
- Test: `b^2*(x-b)+a^2*(x-a)=a*b*x`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-a**3 + a**2*x - a*b*x - b**3 + b**2*x`.
- Counterexample: `a=1, b=1, x=1` gives left `0` and right `1`.

### boyden-algebra-f5ebbe012059

Source lines 6362–6363; family `rational-equations`; human review **pending**.

- Original: `x^2-\frac{x^2-10}{3} = 35-\frac{x^2+50}{5}`
- Test: `x^2-(x^2-10)/3=35-(x^2+50)/5`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. Assume 3 != 0; 5 != 0.
- Exact `left - right`: `13*x**2/15 - 65/3`.
- Counterexample: `x=1` gives left `4` and right `124/5`.

### boyden-algebra-63b7ba5014f2

Source lines 6384–6384; family `quadratic-equations`; human review **pending**.

- Original: `5(3x^2-1) = 11(x^2+1)`
- Test: `5*(3*x^2-1)=11*(x^2+1)`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `4*x**2 - 16`.
- Counterexample: `x=1` gives left `10` and right `22`.

### boyden-algebra-2bea3b58b652

Source lines 6392–6392; family `quadratic-equations`; human review **pending**.

- Original: `(x+3)^2 = 6x+58`
- Test: `(x+3)^2=6*x+58`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `x**2 - 49`.
- Counterexample: `x=1` gives left `16` and right `64`.

### boyden-algebra-2a8eef9d7185

Source lines 6460–6460; family `quadratic-equations`; human review **pending**.

- Original: `x^{2}=10x-21`
- Test: `x^2=10*x-21`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `x**2 - 10*x + 21`.
- Counterexample: `x=1` gives left `1` and right `-11`.

### boyden-algebra-2b02e56aa179

Source lines 6461–6461; family `quadratic-equations`; human review **pending**.

- Original: `23x=120+x^{2}`
- Test: `23*x=120+x^2`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-x**2 + 23*x - 120`.
- Counterexample: `x=1` gives left `23` and right `121`.

### boyden-algebra-4cacf3408049

Source lines 6467–6467; family `quadratic-equations`; human review **pending**.

- Original: `(x+3)(x-3)=8(x+3)`
- Test: `(x+3)*(x-3)=8*(x+3)`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `x**2 - 8*x - 33`.
- Counterexample: `x=1` gives left `-8` and right `32`.

### boyden-algebra-4e1612159403

Source lines 6348–6349; family `cubic-equations`; human review **pending**.

- Original: `7x^2-10 = 5+2x^3`
- Test: `7*x^2-10=5+2*x^3`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-2*x**3 + 7*x**2 - 15`.
- Counterexample: `x=1` gives left `-3` and right `7`.

### boyden-algebra-4d32ba97cc86

Source lines 6569–6569; family `parameter-equations`; human review **pending**.

- Original: `bx-b^{2}=3b^{2}-4bx`
- Test: `b*x-b^2=3*b^2-4*b*x`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `-4*b**2 + 5*b*x`.
- Counterexample: `b=1, x=1` gives left `0` and right `-1`.

### boyden-algebra-4f280d1762c4

Source lines 6728–6728; family `parameter-equations`; human review **pending**.

- Original: `x(a-x)+x(b-x)=2(x-a)(b-x)`
- Test: `x*(a-x)+x*(b-x)=2*(x-a)*(b-x)`
- Proposed codes: `["ALG001"]`; exit status: `1`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. No denominator restrictions.
- Exact `left - right`: `2*a*b - a*x - b*x`.
- Counterexample: `a=1, b=1, x=2` gives left `-4` and right `-2`.

### thompson-calculus-3a1242da97bb

Source lines 5751–5752; family `rational-cancellation`; human review **pending**.

- Original: `y + n\dfrac{y}{n} = 2y.`
- Test: `y+n*(y/n)=2*y`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. Assume n != 0.
- Exact `left - right`: `0`.

### planck-thermodynamics-5d6f62ea4051

Source lines 1307–1308; family `rational-cancellation`; human review **pending**.

- Original: `\frac{\;\;dp\;\;}{\dfrac{dp}{p}} = p,`
- Test: `dp/(dp/p)=p`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Check universal identity only. A sourced exercise with a counterexample is a conditional equation, not an erroneous exercise.
- Assumptions: Commutative scalar arithmetic. Assume dp/p != 0; p != 0.
- Exact `left - right`: `0`.

### planck-thermodynamics-4df852c54f75

Source lines 1140–1141; family `specific-volume`; human review **pending**.

- Original: `\frac{V}{M} = v,`
- Test: `V/M=v`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: V is total volume, M mass, v volume per mass (section 8).
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `V: L^3`; `M: M`; `v: M^-1 L^3`.
- Both sides have exponent vector `[-1, 3, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-10e304d1cb67

Source lines 2353–2354; family `specific-heat`; human review **pending**.

- Original: `\frac{Q}{\Delta\theta} = c_{m}.`
- Test: `Q/dTheta=c_m`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Here Q is heat received per unit mass, not total heat; dTheta represents the printed finite temperature increment (section 46).
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `Q: L^2 T^-2`; `dTheta: Theta`; `c_m: L^2 T^-2 Theta^-1`.
- Both sides have exponent vector `[0, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-a010c1544a6d

Source lines 2874–2875; family `first-law`; human review **pending**.

- Original: `U_{2} - U_{1} = Q + W,`
- Test: `U_2-U_1=Q+W`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: U is total internal energy; Q and W are transferred heat and work (section 67).
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `U_2: M L^2 T^-2`; `U_1: M L^2 T^-2`; `Q: M L^2 T^-2`; `W: M L^2 T^-2`.
- Both sides have exponent vector `[1, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-ba5f1f2be795

Source lines 4717–4718; family `specific-first-law`; human review **pending**.

- Original: `q = du + p\, dv`
- Test: `q=du+p*dv`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Lowercase u and v are energy and volume per mass; q is heat per mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `q: L^2 T^-2`; `du: L^2 T^-2`; `p: M L^-1 T^-2`; `dv: M^-1 L^3`.
- Both sides have exponent vector `[0, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-42f682eb814a

Source lines 6724–6724; family `phase-mass-balance`; human review **pending**.

- Original: `M_{1} + M_{2} + M_{3} = M`
- Test: `M_1+M_2+M_3=M`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: All M quantities are phase masses; M is total mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `M_1: M`; `M_2: M`; `M_3: M`; `M: M`.
- Both sides have exponent vector `[1, 0, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-3a68529243b0

Source lines 8703–8704; family `thermodynamic-potential`; human review **pending**.

- Original: `\Psi = \Phi - \frac{U + pV}{\theta}.`
- Test: `Psi=Phi-(U+p*V)/theta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Phi is total entropy. Psi is the entropy-form potential defined in section 200, not energy.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `Psi: M L^2 T^-2 Theta^-1`; `Phi: M L^2 T^-2 Theta^-1`; `U: M L^2 T^-2`; `p: M L^-1 T^-2`; `V: L^3`; `theta: Theta`.
- Both sides have exponent vector `[1, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-d4695d579997

Source lines 1203–1204; family `gas-temperature-scale`; human review **pending**.

- Original: `T = T_{0} (1 + \alpha t),`
- Test: `T=T_0*(1+alpha*t)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: The source T denotes p times specific volume, not temperature; alpha is thermal expansion per degree.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `T: L^2 T^-2`; `T_0: L^2 T^-2`; `alpha: Theta^-1`; `t: Theta`.
- Both sides have exponent vector `[0, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-6f20e62f73c5

Source lines 2068–2069; family `ideal-gas`; human review **pending**.

- Original: `p = \frac{C_{0} \theta}{v_{0}},`
- Test: `p=C_0*theta/v_0`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: C_0 is the specific gas constant for hydrogen; v_0 is its specific volume.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `p: M L^-1 T^-2`; `C_0: L^2 T^-2 Theta^-1`; `theta: Theta`; `v_0: M^-1 L^3`.
- Both sides have exponent vector `[1, -1, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-4d33dc530033

Source lines 4012–4014; family `isobaric-first-law`; human review **pending**.

- Original: `U_{2} - U_{1} = Q + p_{0} (V_{1} - V_{2}). \Tag{(47)}`
- Test: `U_2-U_1=Q+p_0*(V_1-V_2)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Fixed external pressure multiplies the total volume change; all other terms are energy.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `U_2: M L^2 T^-2`; `U_1: M L^2 T^-2`; `Q: M L^2 T^-2`; `p_0: M L^-1 T^-2`; `V_1: L^3`; `V_2: L^3`.
- Both sides have exponent vector `[1, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-80963961a677

Source lines 6733–6734; family `phase-volume-balance`; human review **pending**.

- Original: `M_{1} v_{1} + M_{2} v_{2} + M_{3} v_{3} = V.`
- Test: `M_1*v_1+M_2*v_2+M_3*v_3=V`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Specific phase volumes multiplied by phase masses sum to total volume.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `M_1: M`; `M_2: M`; `M_3: M`; `v_1: M^-1 L^3`; `v_2: M^-1 L^3`; `v_3: M^-1 L^3`; `V: L^3`.
- Both sides have exponent vector `[0, 3, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-37f9ef604145

Source lines 10208–10209; family `entropy-differential`; human review **pending**.

- Original: `d\Phi = \frac{dU + p\, dV}{\theta},`
- Test: `dPhi=(dU+p*dV)/theta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: dPhi, dU and dV name increments of total entropy, energy and volume; only their dimensions are checked.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dPhi: M L^2 T^-2 Theta^-1`; `dU: M L^2 T^-2`; `p: M L^-1 T^-2`; `dV: L^3`; `theta: Theta`.
- Both sides have exponent vector `[1, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-430cb929aa22

Source lines 1208–1209; family `gas-temperature-scale`; human review **pending**.

- Original: `p = \frac{T_{0}}{v} (1 + \alpha t).`
- Test: `p=(T_0/v)*(1+alpha*t)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: T_0 has dimensions of p times specific volume; t is a temperature coordinate. This does not check Celsius offsets.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `p: M L^-1 T^-2`; `T_0: L^2 T^-2`; `v: M^-1 L^3`; `alpha: Theta^-1`; `t: Theta`.
- Both sides have exponent vector `[1, -1, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-827bba70f280

Source lines 5494–5495; family `carnot-heat-work`; human review **pending**.

- Original: `Q_{1}' = \frac{\theta_{1}}{\theta_{2} - \theta_{1}} W'`
- Test: `Q_1p*(theta_2-theta_1)=theta_1*Wp`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Prime symbols become suffix p. Multiply both sides by the nonzero temperature difference; retain that source-domain restriction.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness. The original denominator product theta_2-theta_1 must remain nonzero.
- Rearrangement: multiply original scalar relation `Q_1p=(theta_1/(theta_2-theta_1))*Wp` by nonzero `theta_2-theta_1`. Exact residual `(old_left-old_right)*multiplier-(new_left-new_right)` is `0`.
- Dimensions: `Q_1p: M L^2 T^-2`; `Wp: M L^2 T^-2`; `theta_1: Theta`; `theta_2: Theta`.
- Both sides have exponent vector `[1, 2, -2, 1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-2d719e31387e

Source lines 1215–1215; family `gas-temperature-scale`; human review **pending**.

- Original: `t + \dfrac{1}{\alpha} = \theta`
- Test: `t+1/alpha=theta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Dimension check of the source's temperature-scale conversion; alpha is nonzero. Numeric origins are not checked.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `t: Theta`; `theta: Theta`; `alpha: Theta^-1`.
- Both sides have exponent vector `[0, 0, 0, 1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-c1a44ebeee0a

Source lines 4806–4807; family `reservoir-entropy`; human review **pending**.

- Original: `d\Phi_{1} = \frac{Q_{1}}{\theta_{1}},`
- Test: `dPhi_1=Q_1/theta_1`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Reservoir entropy increment equals transferred total heat divided by absolute temperature.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dPhi_1: M L^2 T^-2 Theta^-1`; `Q_1: M L^2 T^-2`; `theta_1: Theta`.
- Both sides have exponent vector `[1, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-3439a6971adb

Source lines 1302–1303; family `isothermal-compressibility`; human review **pending**.

- Original: `-\frac{dV}{V} = \frac{dp}{p},`
- Test: `-dV/V=dp/p`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: The two relative changes are dimensionless; pressure and volume are nonzero.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dV: L^3`; `V: L^3`; `dp: M L^-1 T^-2`; `p: M L^-1 T^-2`.
- Both sides have exponent vector `[0, 0, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-943dcd169270

Source lines 6265–6265; family `heat-capacity-ratio`; human review **pending**.

- Original: `\dfrac{c_{p}}{c_{v}} = \gamma`
- Test: `c_p/c_v=gamma`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Both specific heats have the same units; gamma is a dimensionless ratio.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `c_p: L^2 T^-2 Theta^-1`; `c_v: L^2 T^-2 Theta^-1`; `gamma: 1`.
- Both sides have exponent vector `[0, 0, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-92d4856c4122

Source lines 5633–5634; family `reservoir-entropy`; human review **pending**.

- Original: `d\Phi_{0} = -\frac{Q}{\theta},`
- Test: `dPhi_0=-Q/theta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Reservoir entropy sign differs because heat leaves the reservoir; units are unchanged.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dPhi_0: M L^2 T^-2 Theta^-1`; `Q: M L^2 T^-2`; `theta: Theta`.
- Both sides have exponent vector `[1, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-529196ccfdec

Source lines 1481–1482; family `mixture-gas-constant`; human review **pending**.

- Original: `C = \frac{C_{1}M_{1} + C_{2}M_{2}}{M_{1} + M_{2}},`
- Test: `C*(M_1+M_2)=C_1*M_1+C_2*M_2`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: C quantities are specific gas constants (section 20). Multiply the original relation by nonzero total mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness. The original denominator product M_1+M_2 must remain nonzero.
- Rearrangement: multiply original scalar relation `C=(C_1*M_1+C_2*M_2)/(M_1+M_2)` by nonzero `M_1+M_2`. Exact residual `(old_left-old_right)*multiplier-(new_left-new_right)` is `0`.
- Dimensions: `C: L^2 T^-2 Theta^-1`; `C_1: L^2 T^-2 Theta^-1`; `C_2: L^2 T^-2 Theta^-1`; `M_1: M`; `M_2: M`.
- Both sides have exponent vector `[1, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-c5b75ec7231e

Source lines 1553–1554; family `van-der-waals`; human review **pending**.

- Original: `p = \frac{R\theta}{v - b} - \frac{a}{v^{2}},`
- Test: `p*(v-b)*v^2=R*theta*v^2-a*(v-b)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: R is substance-specific; b is specific volume and a has pressure times specific-volume-squared units (section 24). Multiply by (v-b)*v^2, retaining v!=0 and v!=b.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness. The original denominator product (v-b)*v^2 must remain nonzero.
- Rearrangement: multiply original scalar relation `p=R*theta/(v-b)-a/v^2` by nonzero `(v-b)*v^2`. Exact residual `(old_left-old_right)*multiplier-(new_left-new_right)` is `0`.
- Dimensions: `p: M L^-1 T^-2`; `R: L^2 T^-2 Theta^-1`; `theta: Theta`; `v: M^-1 L^3`; `b: M^-1 L^3`; `a: M^-1 L^5 T^-2`.
- Both sides have exponent vector `[-2, 8, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-6d212b87b1ba

Source lines 1584–1586; family `clausius-equation`; human review **pending**.

- Original: `p = \frac{R\theta}{v - a} - \frac{c}{\theta(v + b)^{2}}. \Tag{(12)}`
- Test: `p*theta*(v-a)*(v+b)^2=R*theta^2*(v+b)^2-c*(v-a)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Section 25's a,b are specific volumes and c has pressure times temperature times specific-volume-squared units. Multiply by theta*(v-a)*(v+b)^2, retaining every original nonzero denominator.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness. The original denominator product theta*(v-a)*(v+b)^2 must remain nonzero.
- Rearrangement: multiply original scalar relation `p=R*theta/(v-a)-c/(theta*(v+b)^2)` by nonzero `theta*(v-a)*(v+b)^2`. Exact residual `(old_left-old_right)*multiplier-(new_left-new_right)` is `0`.
- Dimensions: `p: M L^-1 T^-2`; `R: L^2 T^-2 Theta^-1`; `theta: Theta`; `v: M^-1 L^3`; `a: M^-1 L^3`; `b: M^-1 L^3`; `c: M^-1 L^5 T^-2 Theta`.
- Both sides have exponent vector `[-2, 8, -2, 1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-94ffa269abce

Source lines 3410–3412; family `specific-heat`; human review **pending**.

- Original: `du = c_{v} · d\theta. \Tag{(32)}`
- Test: `du=c_v*dTheta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: For a perfect gas u is energy per mass; c_v is heat capacity per mass and temperature.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `du: L^2 T^-2`; `c_v: L^2 T^-2 Theta^-1`; `dTheta: Theta`.
- Both sides have exponent vector `[0, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-daf616be1910

Source lines 7134–7136; family `phase-free-energy`; human review **pending**.

- Original: `\frac{df_{2}}{d\theta} - \frac{df_{1}}{d\theta} = (v_{1} - v_{2})\, \frac{dp_{1}}{d\theta} + p_{1}\left(\frac{dv_{1}}{d\theta} - \frac{dv_{2}}{d\theta}\right).`
- Test: `df_2/dTheta-df_1/dTheta=(v_1-v_2)*dp_1/dTheta+p_1*(dv_1/dTheta-dv_2/dTheta)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: f is free energy per mass. Each quotient names a derivative's dimensional ratio; no differentiation is performed.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `df_1: L^2 T^-2`; `df_2: L^2 T^-2`; `v_1: M^-1 L^3`; `v_2: M^-1 L^3`; `dv_1: M^-1 L^3`; `dv_2: M^-1 L^3`; `dp_1: M L^-1 T^-2`; `p_1: M L^-1 T^-2`; `dTheta: Theta`.
- Both sides have exponent vector `[0, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-969b2159364a

Source lines 7156–7157; family `clapeyron`; human review **pending**.

- Original: `\phi_{1} - \phi_{2} = (v_{1} - v_{2})\, \frac{dp_{1}}{d\theta},`
- Test: `phi_1-phi_2=(v_1-v_2)*dp_1/dTheta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: phi is entropy per mass; pressure derivative times specific volume has the same dimensions.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `phi_1: L^2 T^-2 Theta^-1`; `phi_2: L^2 T^-2 Theta^-1`; `v_1: M^-1 L^3`; `v_2: M^-1 L^3`; `dp_1: M L^-1 T^-2`; `dTheta: Theta`.
- Both sides have exponent vector `[0, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-03e000f6654b

Source lines 7160–7162; family `clapeyron`; human review **pending**.

- Original: `(u_{1} - u_{2}) + p_{1} (v_{1} - v_{2}) = \theta (v_{1} - v_{2})\, \frac{dp_{1}}{d\theta}. \Tag{(109)}`
- Test: `(u_1-u_2)+p_1*(v_1-v_2)=theta*(v_1-v_2)*dp_1/dTheta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Internal-energy difference and pressure-volume work are per mass; multiplying an entropy change by temperature yields energy per mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `u_1: L^2 T^-2`; `u_2: L^2 T^-2`; `p_1: M L^-1 T^-2`; `dp_1: M L^-1 T^-2`; `v_1: M^-1 L^3`; `v_2: M^-1 L^3`; `theta: Theta`; `dTheta: Theta`.
- Both sides have exponent vector `[0, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-14dc1d1fb72e

Source lines 9269–9270; family `clapeyron`; human review **pending**.

- Original: `L = \theta\, \frac{dp}{d\theta} (v'' - v'),`
- Test: `L=theta*(dp/dTheta)*(v_pp-v_p)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: L is latent heat per mass, not length; p/pp preserve the two prime-indexed phase volumes.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `L: L^2 T^-2`; `theta: Theta`; `dTheta: Theta`; `dp: M L^-1 T^-2`; `v_pp: M^-1 L^3`; `v_p: M^-1 L^3`.
- Both sides have exponent vector `[0, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-c240af04554a

Source lines 7224–7225; family `clapeyron`; human review **pending**.

- Original: `\frac{p_{1} (v_{1} - v_{2})}{L} = \frac{p_{1}}{\theta\, \dfrac{dp_{1}}{d\theta}}.`
- Test: `p_1*(v_1-v_2)/L=p_1/(theta*(dp_1/dTheta))`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Both ratios are dimensionless; denominators are assumed nonzero. Related Clapeyron formulas belong to one family.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `p_1: M L^-1 T^-2`; `dp_1: M L^-1 T^-2`; `v_1: M^-1 L^3`; `v_2: M^-1 L^3`; `L: L^2 T^-2`; `theta: Theta`; `dTheta: Theta`.
- Both sides have exponent vector `[0, 0, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-4540035eaa7d

Source lines 9325–9326; family `phase-volume-balance`; human review **pending**.

- Original: `V = v' (M_{1}' + M_{2}') + v'' M_{1}'' + v''' M_{2}''',`
- Test: `V=v_p*(M_1p+M_2p)+v_pp*M_1pp+v_ppp*M_2ppp`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Each prime-marked phase retains a different ASCII suffix; specific volumes multiply the corresponding masses.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `V: L^3`; `v_p: M^-1 L^3`; `v_pp: M^-1 L^3`; `v_ppp: M^-1 L^3`; `M_1p: M`; `M_2p: M`; `M_1pp: M`; `M_2ppp: M`.
- Both sides have exponent vector `[0, 3, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-8fe652c61061

Source lines 9345–9346; family `multicomponent-clapeyron`; human review **pending**.

- Original: `L = \theta\, \frac{dp}{d\theta} \bigl(v'' + cv''' - (1 + c)v'\bigr).`
- Test: `L=theta*(dp/dTheta)*(v_pp+c*v_ppp-(1+c)*v_p)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: c is the mass ratio in the source; all bracketed terms are specific volumes and L is heat per mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `L: L^2 T^-2`; `theta: Theta`; `dTheta: Theta`; `dp: M L^-1 T^-2`; `v_pp: M^-1 L^3`; `v_ppp: M^-1 L^3`; `v_p: M^-1 L^3`; `c: 1`.
- Both sides have exponent vector `[0, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-10f2b97c8313

Source lines 7373–7374; family `latent-entropy`; human review **pending**.

- Original: `\frac{L}{\theta} = \phi_{1} - \phi_{2}.`
- Test: `L/theta=phi_1-phi_2`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Latent heat per mass divided by temperature gives entropy per mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `L: L^2 T^-2`; `theta: Theta`; `phi_1: L^2 T^-2 Theta^-1`; `phi_2: L^2 T^-2 Theta^-1`.
- Both sides have exponent vector `[0, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-5a6f4ec90fc0

Source lines 7478–7479; family `latent-heat-capacity`; human review **pending**.

- Original: `(c_{p})_{1} - (c_{p})_{2} = \frac{dL}{d\theta}.`
- Test: `c_p1-c_p2=dL/dTheta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: The source explicitly calls this relation approximate after neglecting liquid volume and treating the vapour as ideal; its specific-heat units remain consistent.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `c_p1: L^2 T^-2 Theta^-1`; `c_p2: L^2 T^-2 Theta^-1`; `dL: L^2 T^-2`; `dTheta: Theta`.
- Both sides have exponent vector `[0, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-27d1b346276b

Source lines 7529–7530; family `path-heat-capacity`; human review **pending**.

- Original: `c = \frac{du}{d\theta} + p\, \frac{dv}{d\theta}.`
- Test: `c=du/dTheta+p*dv/dTheta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: This is specific heat along the source's constrained path; energy and work increments are per mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `c: L^2 T^-2 Theta^-1`; `du: L^2 T^-2`; `dTheta: Theta`; `p: M L^-1 T^-2`; `dv: M^-1 L^3`.
- Both sides have exponent vector `[0, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-ee1e469a97a2

Source lines 3701–3702; family `carnot-volume-ratios`; human review **pending**.

- Original: `\frac{v_{2}'}{v_{2}} = \frac{v_{1}'}{v_{1}},`
- Test: `v_2p/v_2=v_1p/v_1`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: All v quantities are specific volumes. Prime and state suffixes preserve source identity.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `v_2p: M^-1 L^3`; `v_2: M^-1 L^3`; `v_1p: M^-1 L^3`; `v_1: M^-1 L^3`.
- Both sides have exponent vector `[0, 0, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-701735c0cd36

Source lines 7592–7593; family `latent-heat-capacity`; human review **pending**.

- Original: `h_{1} = (c_{p})_{2} + \frac{dL}{d\theta} - \frac{L}{\theta}.`
- Test: `h_1=c_p2+dL/dTheta-L/theta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: h_1 is the source's specific heat along the saturation curve, not enthalpy.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `h_1: L^2 T^-2 Theta^-1`; `c_p2: L^2 T^-2 Theta^-1`; `dL: L^2 T^-2`; `L: L^2 T^-2`; `dTheta: Theta`; `theta: Theta`.
- Both sides have exponent vector `[0, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-0bd100064dff

Source lines 9865–9867; family `solution-temperature-shift`; human review **pending**.

- Original: `\theta - \theta_{0} = \frac{c\theta^{2} \varphi}{L}. \Tag{(183)}`
- Test: `theta-theta_0=c*theta^2*varphi/L`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: c is a mass concentration ratio, varphi an entropy-per-mass function, and L latent heat per mass.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `theta: Theta`; `theta_0: Theta`; `c: 1`; `varphi: L^2 T^-2 Theta^-1`; `L: L^2 T^-2`.
- Both sides have exponent vector `[0, 0, 0, 1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-01423e0201db

Source lines 10065–10067; family `osmotic-pressure`; human review **pending**.

- Original: `P = \frac{c\theta\varphi}{v}. \Tag{(190)}`
- Test: `P=c*theta*varphi/v`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: The solution's osmotic pressure P uses the source's dimensionless mass ratio c and specific volume v.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `P: M L^-1 T^-2`; `c: 1`; `theta: Theta`; `varphi: L^2 T^-2 Theta^-1`; `v: M^-1 L^3`.
- Both sides have exponent vector `[1, -1, -2, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-5b3e17f5dba3

Source lines 3042–3043; family `kinematic-velocity`; human review **pending**.

- Original: `v = \dfrac{dy}{dt}.`
- Test: `v=dy/dt`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: y denotes travelled distance and t time in the surrounding motion example; differentials retain those units.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `v: L T^-1`; `dy: L`; `dt: T`.
- Both sides have exponent vector `[0, 1, -1, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-04404005bc21

Source lines 1480–1480; family `right-triangle`; human review **pending**.

- Original: `x^2 + y^2 = l^2`
- Test: `x^2+y^2=l^2`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: The source's sides x,y and hypotenuse l are lengths; only dimensional consistency is asserted.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `x: L`; `y: L`; `l: L`.
- Both sides have exponent vector `[0, 2, 0, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-79ec7d2af9e2

Source lines 7367–7367; family `cone-volume`; human review **pending**.

- Original: `V=\frac{1}{3} \pi r^2 h`
- Test: `V=(1/3)*pi*r^2*h`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Radius and height are lengths, pi is dimensionless and V is volume.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `V: L^3`; `pi: 1`; `r: L`; `h: L`.
- Both sides have exponent vector `[0, 3, 0, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-53ccb9dfbef3

Source lines 7382–7382; family `cone-volume`; human review **pending**.

- Original: `dV = \dfrac{2\pi}{3} rh\, dV + \dfrac{\pi}{3} r^2\, dh`
- Test: `dV=(2*pi/3)*r*h*dV+(pi/3)*r^2*dh`
- Proposed codes: `["DIM002"]`; exit status: `1`.
- Meaning: Pinned source text repeats dV in the first RHS term: that term has L^5 but the second has L^3. Preserve the transcription; do not silently replace it with dr.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dV: L^3`; `pi: 1`; `r: L`; `h: L`; `dh: L`.
- Incompatible sum: `2 * pi / 3 * r * h * dV + pi / 3 * r ** 2 * dh` combines vectors `[0, 5, 0, 0]` and `[0, 3, 0, 0]`.

### thompson-calculus-5cc9a8b86e21

Source lines 7479–7479; family `box-surface`; human review **pending**.

- Original: `S=xy + \dfrac{2V}{x} + \dfrac{2V}{y}`
- Test: `S=x*y+2*V/x+2*V/y`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: x,y are side lengths; V is fixed volume and S the surface-area expression.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `S: L^2`; `x: L`; `y: L`; `V: L^3`.
- Both sides have exponent vector `[0, 2, 0, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-f81c17612fb7

Source lines 8859–8860; family `circle-geometry`; human review **pending**.

- Original: `y^2 = r^2 - x^2.`
- Test: `y^2=r^2-x^2`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Coordinates and circle radius are lengths; squared terms have area dimensions.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `y: L`; `r: L`; `x: L`.
- Both sides have exponent vector `[0, 2, 0, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-972b7b334413

Source lines 2394–2395; family `product-differential`; human review **pending**.

- Original: `\dfrac{dy}{dx} = u\, \dfrac{dv}{dx} + v\, \dfrac{du}{dx}.`
- Test: `dy/dx=u*(dv/dx)+v*(du/dx)`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: A dimensional specialization of y=u*v: u,v,x have length units and y area. The derivative rule is not algebraically proved by this test.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dy: L^2`; `dx: L`; `u: L`; `v: L`; `du: L`; `dv: L`.
- Both sides have exponent vector `[0, 1, 0, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-00742805093f

Source lines 2390–2391; family `product-differential`; human review **pending**.

- Original: `dy = u · dv + v · du;`
- Test: `dy=u*dv+v*du`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Use y=u*v with u and v lengths and y area; named increments test dimensional homogeneity only.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dy: L^2`; `u: L`; `v: L`; `du: L`; `dv: L`.
- Both sides have exponent vector `[0, 2, 0, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-ac0b77c564ba

Source lines 1668–1668; family `constant-acceleration`; human review **pending**.

- Original: `y = b + \frac{1}{2} at^2`
- Test: `y=b+(1/2)*a*t^2`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: The source names time as the independent variable. For this dimensional specialization, take y and b as lengths and a as acceleration; the text does not independently specify those latter units.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `y: L`; `b: L`; `a: L T^-2`; `t: T`.
- Both sides have exponent vector `[0, 1, 0, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-768e03e2c4b1

Source lines 5637–5638; family `reservoir-entropy`; human review **pending**.

- Original: `d\Phi_{0} = -\frac{dU - W}{\theta}.`
- Test: `dPhi_0=-(dU-W)/theta`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: The source expresses the reservoir's entropy change using total system energy and work.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `dPhi_0: M L^2 T^-2 Theta^-1`; `dU: M L^2 T^-2`; `W: M L^2 T^-2`; `theta: Theta`.
- Both sides have exponent vector `[1, 2, -2, -1]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-0de5b452c9f5

Source lines 5457–5458; family `carnot-heat-work`; human review **pending**.

- Original: `Q_{2} = W' + Q_{1}'`
- Test: `Q_2=Wp+Q_1p`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Heat and work are total energy transfers; prime suffixes keep distinct source quantities.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `Q_2: M L^2 T^-2`; `Wp: M L^2 T^-2`; `Q_1p: M L^2 T^-2`.
- Both sides have exponent vector `[1, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### planck-thermodynamics-a5fa2d8533f6

Source lines 4787–4788; family `first-law`; human review **pending**.

- Original: `Q + W = dU,`
- Test: `Q+W=dU`
- Proposed codes: `[]`; exit status: `0`.
- Meaning: Q and W are transfers during an infinitesimal change; dU names the total internal-energy increment.
- Assumptions: Declared quantity meanings; all denominators nonzero. Dimensional homogeneity is necessary, not sufficient, for physical correctness.
- Dimensions: `Q: M L^2 T^-2`; `W: M L^2 T^-2`; `dU: M L^2 T^-2`.
- Both sides have exponent vector `[1, 2, -2, 0]`; all additions/subtractions combine matching vectors.

### thompson-calculus-8450a4bfe64e

Source lines 9023–9024; family `integration-by-parts`; human review **pending**.

- Original: `\int u\, dx = ux - \int x\, du + C.`
- Test: `\int u\, dx = ux - \int x\, du + C`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: Integral operators remain unsupported; their identity is not checked.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-75f3dbb34ee1

Source lines 7328–7329; family `partial-differentials`; human review **pending**.

- Original: `dy = \frac{\partial y}{\partial u}\, du + \dfrac{\partial y}{\partial v}\, dv;`
- Test: `dy = \frac{\partial y}{\partial u}\, du + \dfrac{\partial y}{\partial v}\, dv`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: Partial derivative notation is outside the scalar grammar.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-9f1d1909d114

Source lines 7354–7354; family `variable-exponent`; human review **pending**.

- Original: `z = x^y`
- Test: `z = x^y`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: A variable exponent is outside the documented integer-power grammar.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-3a02c1f501c1

Source lines 1407–1408; family `decimal-approximation`; human review **pending**.

- Original: `\frac{dy}{dx} = \frac{1}{1.73}.`
- Test: `\frac{dy}{dx} = \frac{1}{1.73}`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: The decimal denominator remains literal unsupported notation.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### planck-thermodynamics-713f14ee5e2e

Source lines 11979–11979; family `chemical-equilibrium-log`; human review **pending**.

- Original: `\log K = 0`
- Test: `\log K = 0`
- Proposed codes: `["PARSE021"]`; exit status: `0`.
- Meaning: Logarithm is a documented unsupported function.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-121f8a5849ee

Source lines 6215–6216; family `exponential`; human review **pending**.

- Original: `\frac{dx}{dy} = \epsilon^y,`
- Test: `\frac{dx}{dy} = \epsilon^y`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: The source's Greek exponential base with a symbolic exponent is unsupported.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### planck-thermodynamics-fcf0619fd27b

Source lines 6462–6464; family `cube-root`; human review **pending**.

- Original: `v = \frac{c_{p}^{(0)} \theta}{3p} \left(\sqrt[3]{1 - \frac{3\alpha p}{\theta^{3}}} + \beta\right). \Tag{(89)}`
- Test: `v = \frac{c_{p}^{(0)} \theta}{3p} \left(\sqrt[3]{1 - \frac{3\alpha p}{\theta^{3}}} + \beta\right)`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: Indexed cube roots and indexed coefficients are outside the documented scalar grammar.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### planck-thermodynamics-7ddcf7d688ed

Source lines 2708–2708; family `decimal-approximation`; human review **pending**.

- Original: `423.55 × 1.007 = 427`
- Test: `423.55 × 1.007 = 427`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: The source uses decimals and a multiplication glyph; do not treat its rounded equality as exact arithmetic.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-7c6ec8406e52

Source lines 6919–6920; family `trigonometry`; human review **pending**.

- Original: `y= \sin \theta.`
- Test: `y= \sin \theta`
- Proposed codes: `["PARSE021"]`; exit status: `0`.
- Meaning: Sine is a documented unsupported function.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-de630763755d

Source lines 3518–3518; family `symbolic-radical`; human review **pending**.

- Original: `y = \sqrt{a+x}`
- Test: `y = \sqrt{a+x}`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: The radicand contains a symbol; only numeric perfect-square radicals are supported.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-4494c4ff821c

Source lines 7828–7829; family `symbolic-antiderivative`; human review **pending**.

- Original: `y = \frac{1}{n + 1} x^{n+1} + C.`
- Test: `y = \frac{1}{n + 1} x^{n+1} + C`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: Symbolic exponents and a non-monomial denominator remain unsupported.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-6206efcc63da

Source lines 5076–5076; family `signed-radical`; human review **pending**.

- Original: `P = ±\sqrt{\dfrac{b}{a}} - c`
- Test: `P = ±\sqrt{\dfrac{b}{a}} - c`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: The plus-or-minus glyph and symbolic square root are unsupported.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### thompson-calculus-699bc3932853

Source lines 1479–1479; family `angle-notation`; human review **pending**.

- Original: `\dfrac{y}{x} = \tan 30°`
- Test: `\dfrac{y}{x} = \tan 30°`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: The degree glyph is outside the tokenizer's supported notation.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### planck-thermodynamics-d43a1fd24828

Source lines 1947–1948; family `proportions`; human review **pending**.

- Original: `28 : 14 : 9\tfrac{1}{3} : 7 : 5\tfrac{3}{5} = 60 : 30 : 20 : 15 : 12.`
- Test: `28 : 14 : 9\tfrac{1}{3} : 7 : 5\tfrac{3}{5} = 60 : 30 : 20 : 15 : 12`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: Colon-separated proportions and mixed-number notation are outside the scalar grammar.
- Assumptions: No mathematical truth judgment; informational skip is expected.

### planck-thermodynamics-3020cee46caf

Source lines 10950–10951; family `mixture-sequence`; human review **pending**.

- Original: `V' = (n_{0} + 1) v_{0} + n_{1} v_{1} + n_{2} v_{2} + \dots`
- Test: `V' = (n_{0} + 1) v_{0} + n_{1} v_{1} + n_{2} v_{2} + \dots`
- Proposed codes: `["PARSE020"]`; exit status: `0`.
- Meaning: The source's prime glyphs and unfinished indexed sequence cannot be checked as finite scalar arithmetic.
- Assumptions: No mathematical truth judgment; informational skip is expected.
