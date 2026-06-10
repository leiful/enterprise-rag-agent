# Manual RAG Test Questions

This suite is designed for the three uploaded PDFs:

- `employee_handbook_City_of_Beaverton_2025.pdf`
- `drug_label_Cosentyx_prescribing_information.pdf`
- `microwave_manual_Midea_XM044KYYGE.pdf`

Use each question in chat. Score both retrieval and answer quality.

## Scoring

- 2 = Correct answer, grounded in the right document, with usable citation/source.
- 1 = Partly correct, but missing a key condition, weak citation, or retrieved noisy evidence.
- 0 = Wrong answer, hallucination, wrong document, or no answer when the document contains the answer.

For no-answer questions:

- 2 = Clearly says the uploaded documents do not contain enough evidence.
- 1 = Mostly refuses but adds unsupported speculation.
- 0 = Invents an answer.

## Questions

| ID | Type | Question | Expected answer points | Expected source |
|---|---|---|---|---|
| E01 | Direct fact | According to the City of Beaverton employee handbook, when is a non-exempt employee required to take a meal period? | At least a 30-minute unpaid meal period is required when the work period is six hours or greater; no meal period is required if the work period is less than six hours. | Employee handbook, section 3.9, page 17 |
| E02 | Direct fact | What rest break does the handbook require for non-exempt employees for each four-hour work segment? | A paid, uninterrupted 15-minute rest break for every four-hour segment or major portion thereof, typically in the middle of the segment. | Employee handbook, section 3.9, page 17 |
| E03 | Detail condition | Can meal periods and rest breaks be combined or skipped so an employee can arrive late or leave early? | No. Meal periods and rest breaks may not be taken together, at the start/end of the workday, or skipped to start late or leave early. | Employee handbook, section 3.9, page 17 |
| E04 | Detail condition | Under the handbook, can non-exempt employees work overtime without supervisor authorization? | No. Overtime must be specifically authorized by a supervisor or manager, preferably in writing, except in an emergency; unauthorized overtime may lead to discipline. | Employee handbook, section 3.11.2, page 18 |
| E05 | Detail fact | What is the maximum amount of compensatory time that can be banked? | Up to 100 hours. | Employee handbook, section 3.11.3, page 18 |
| E06 | Detail condition | For overtime calculations, do paid hours not actually worked count toward the 40-hour work week? | Yes, examples include sick, vacation, PTO, holidays, and family leave, unless a collective bargaining agreement says otherwise. | Employee handbook, section 3.11.1, page 18 |
| E07 | Policy hierarchy | If a collective bargaining agreement contradicts the employee handbook, which controls? | The collective bargaining agreement provision controls. | Employee handbook, welcome/introduction, page ii |
| E08 | Remote work | Does being approved for a flexible work schedule automatically make an employee eligible for remote work? | No. Some classifications may not be eligible for remote work even if approved for a flexible schedule. | Employee handbook, section 3.8, page 17 |
| E09 | Lactation break | For what child age does the city provide reasonable rest periods for expression of breast milk? | For an employee's child who is 18 months old or younger. | Employee handbook, section 3.10, page 17 |
| E10 | Benefits/probation | Are probationary employees generally entitled to educational assistance? | Generally no; probationary employees are generally not entitled to educational assistance. | Employee handbook, section 3.6, page 15 |
| D01 | Direct fact | What is COSENTYX indicated to treat in plaque psoriasis patients? | Moderate to severe plaque psoriasis in adults and pediatric patients 6 years and older who are candidates for systemic therapy or phototherapy. | COSENTYX label, section 1.1, page 4 |
| D02 | Direct fact | What are the most common adverse reactions listed for COSENTYX? | Nasopharyngitis, diarrhea, and upper respiratory tract infection. | COSENTYX label highlights, page 2 |
| D03 | Safety warning | What should be done if a serious infection develops during COSENTYX treatment? | Discontinue COSENTYX until the infection resolves. | COSENTYX label warnings, page 1 |
| D04 | Pre-treatment check | What should be evaluated before initiating COSENTYX treatment? | Evaluate patients for tuberculosis; also complete age-appropriate vaccinations before initiation. | COSENTYX label highlights/section 2.1, page 1 |
| D05 | Immunization warning | What does the label say about live vaccines for patients treated with COSENTYX? | Avoid use of live vaccines in patients treated with COSENTYX. | COSENTYX label warnings, page 1 |
| D06 | Contraindication | What is the listed contraindication for COSENTYX? | Serious hypersensitivity to secukinumab or any excipients in COSENTYX. | COSENTYX label highlights, page 1 |
| D07 | Dosing detail | What is the adult plaque psoriasis subcutaneous dosage schedule for COSENTYX? | 300 mg by subcutaneous injection at Weeks 0, 1, 2, 3, and 4, then every 4 weeks thereafter; each 300 mg dose can be one 300 mg injection or two 150 mg injections. | COSENTYX label, section 2.3, page 5 |
| D08 | Pediatric dosing | For pediatric plaque psoriasis patients 6 years and older, what dose is recommended below 50 kg and at or above 50 kg? | Below 50 kg: 75 mg. At or above 50 kg: 150 mg. | COSENTYX label, section 2.3, page 5 |
| D09 | Route limitation | For which adult conditions may COSENTYX intravenous infusion be administered? | Only adults with PsA, AS, and nr-axSpA. | COSENTYX label, section 2.2/2.12, page 5 |
| D10 | Crohn distractor | Is COSENTYX approved for treatment of Crohn's disease? | No. The label says COSENTYX is not approved for Crohn's disease. | COSENTYX label, IBD warning, page 9 |
| M01 | Electrical requirement | What electrical supply does the microwave manual require? | 120 volt, 60 Hz, AC only, 15 amp or more protected electrical supply; separate circuit serving only the microwave is recommended. | Microwave manual, electrical requirements, page 4 |
| M02 | Safety rule | Does the microwave manual allow using an extension cord? | No. It says do not use an extension cord. If the cord is too short, have a qualified electrician or serviceman install an outlet nearby. | Microwave manual, page 4 |
| M03 | Grounding safety | What does the manual say about the grounding pin? | Do not cut or remove the grounding pin under any circumstances. | Microwave manual, page 4 |
| M04 | Turntable rule | Can the microwave be used without the turntable and support? | No. The manual says never use the microwave without the turntable and support. | Microwave manual, page 6 |
| M05 | Child lock | How do you turn the microwave control lock on or off? | Touch and hold the Stop/Cancel pad for more than 3 seconds. The lock icon appears with 2 beeps when turned on and disappears when turned off. | Microwave manual, manual cooking/control lock, page 9 |
| M06 | Ready Set | How can you quickly heat for 1, 2, or 3 minutes at 100% power? | Touch number pad 1, 2, or 3 for the desired minutes of cook time. | Microwave manual, Ready Set, page 9 |
| M07 | Service check | Before calling service, what water test does the manual suggest? | Place one cup of water in a glass measuring cup, close the door, and operate for one minute at HIGH 100%; check light, display, turntable, and whether water is warm. | Microwave manual, Service Call Check, page 21 |
| M08 | Output power | What is the microwave output power listed in the specifications? | 900 W. | Microwave manual, Specifications, page 21 |
| M09 | Popcorn safety | Does the manual allow popping popcorn in regular brown bags or glass bowls? | No. It says not to pop popcorn in regular brown bags or glass bowls; use specially bagged microwave popcorn. | Microwave manual, food safety table, page 6 |
| X01 | Cross-document routing | Which uploaded document should answer a question about live vaccines, and what is the answer? | COSENTYX drug label; avoid live vaccines in patients treated with COSENTYX. | COSENTYX label |
| X02 | Cross-document routing | Which uploaded document should answer a question about using an extension cord, and what is the answer? | Microwave manual; do not use an extension cord. | Microwave manual |
| X03 | Cross-document routing | Which uploaded document should answer a question about remote work eligibility, and what is the answer? | Employee handbook; flexible schedule approval does not automatically mean remote work eligibility. | Employee handbook |
| X04 | Cross-document comparison | Compare how the employee handbook and microwave manual handle unauthorized actions: unauthorized overtime vs. DIY microwave service. | Handbook: unauthorized overtime may lead to discipline; microwave manual: the oven should never be serviced by a do-it-yourself repair person and should be serviced by qualified personnel. | Employee handbook and microwave manual |
| N01 | No-answer/refusal | According to the uploaded documents, what is the recommended COSENTYX dose for treating Crohn's disease? | Should refuse: the documents say COSENTYX is not approved for Crohn's disease, so no recommended dose is provided. | COSENTYX label |
| N02 | No-answer/refusal | According to the uploaded documents, what is the City of Beaverton's 2026 remote work policy? | Should refuse: the uploaded handbook is effective April 2025 and points to the Remote Work Policy/HR for more information; it does not provide a 2026 remote work policy. | Employee handbook |
| N03 | No-answer/refusal | According to the uploaded documents, what is the microwave's Wi-Fi pairing procedure? | Should refuse: the microwave manual does not contain Wi-Fi pairing instructions. | Microwave manual |
| N04 | No-answer/refusal | Based only on the uploaded documents, what is the exact cost of COSENTYX per dose? | Should refuse: the drug label does not provide pricing. | COSENTYX label |

## Suggested Test Runs

1. Run all questions with normal chat settings and ask the model to cite sources.
2. For each question, record: answer score, source score, top retrieved document, and whether the answer abstained when needed.
3. Pay special attention to cross-document questions. They reveal whether retrieval routes to the right PDF or mixes unrelated chunks.
4. After this baseline, repeat the same questions after changing chunk size or semantic chunking settings.
