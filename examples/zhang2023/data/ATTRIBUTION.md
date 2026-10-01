# Attribution: the 256 Stack Overflow threads

`threads.csv` holds 256 Stack Overflow threads (questions with their answers and comments) that mention GitHub Copilot.
They are the posts Zhang et al. (2023) selected for their study of GitHub Copilot that still existed when we rebuilt them;
the other 47 of their 303 posts have been deleted from Stack Overflow.

## License

Stack Overflow content is licensed under the Creative Commons Attribution-ShareAlike license, CC BY-SA 4.0
(https://creativecommons.org/licenses/by-sa/4.0/). Posts and edits contributed before 2 May 2018 were licensed under
CC BY-SA 3.0, and before 8 April 2011 under CC BY-SA 2.5; Stack Overflow's licensing page explains which version applies
to which contribution (https://stackoverflow.com/help/licensing). This file and `threads.csv` are shared under
CC BY-SA 4.0 in turn.

Each thread was written by the people named on its Stack Overflow page: the question's author (listed below) and the
authors of its answers, comments and edits. The link of each thread leads to that page and its full list of contributors.

## What we changed

- Each thread was **rebuilt as it stood on 18 June 2023** (the day Zhang et al. searched Stack Overflow) from its revision
  history through the public Stack Exchange API: the title and question as revised by then, and the answers and comments
  posted by then. Later answers, comments and edits are left out.
- The HTML was converted to plain text. **Code blocks were replaced by `[code]`** (inline code longer than 60 characters
  too), and images by `[image]`. Nothing else was shortened or truncated.
- One row per thread: `uid` (our id, U001 to U256), `so_question_id`, `link`, `author` (the question's author), `created`
  (the question's creation date) and `text` (title, question, answers and comments, each labelled).

## What is not here

Zhang et al.'s spreadsheet and their labels are not included: they are not ours to redistribute. To compare with their
categories, use their paper and their dataset:

Beiqi Zhang, Peng Liang, Xiyu Zhou, Aakash Ahmad and Muhammad Waseem. *Demystifying Practices, Challenges and Expected
Features of Using GitHub Copilot.* International Journal of Software Engineering and Knowledge Engineering 33(11-12), 2023.
Dataset: Zenodo, doi:10.5281/zenodo.8123303.

## The threads

| uid | Question author | Asked | Link |
|---|---|---|---|
| U001 | Robin Rodricks | 2009-08-31 | https://stackoverflow.com/questions/1358510 |
| U002 | Mark W | 2011-04-18 | https://stackoverflow.com/questions/5704712 |
| U003 | user1217380 | 2012-03-27 | https://stackoverflow.com/questions/9897306 |
| U004 | blitzmann | 2017-05-02 | https://stackoverflow.com/questions/43728431 |
| U005 | kett | 2018-04-09 | https://stackoverflow.com/questions/49729184 |
| U006 | Catfish | 2019-12-05 | https://stackoverflow.com/questions/59200189 |
| U007 | Luka Radic | 2020-09-27 | https://stackoverflow.com/questions/64086068 |
| U008 | Green Cappy | 2020-11-20 | https://stackoverflow.com/questions/64931385 |
| U009 | zain | 2021-07-02 | https://stackoverflow.com/questions/68226649 |
| U010 | Jayy | 2021-07-04 | https://stackoverflow.com/questions/68243449 |
| U011 | harunB10 | 2021-07-05 | https://stackoverflow.com/questions/68253302 |
| U012 | Aviral | 2021-07-05 | https://stackoverflow.com/questions/68258732 |
| U013 | Bajdzis | 2021-07-05 | https://stackoverflow.com/questions/68260233 |
| U014 | human | 2021-07-06 | https://stackoverflow.com/questions/68264645 |
| U015 | Victor Hugo Terceros | 2021-07-09 | https://stackoverflow.com/questions/68323142 |
| U016 | canaan seaton | 2021-07-12 | https://stackoverflow.com/questions/68347605 |
| U017 | KReEd | 2021-07-16 | https://stackoverflow.com/questions/68409055 |
| U018 | dudulu | 2021-07-17 | https://stackoverflow.com/questions/68418600 |
| U019 | user14265379 | 2021-07-23 | https://stackoverflow.com/questions/68496733 |
| U020 | norbekoff | 2021-07-26 | https://stackoverflow.com/questions/68528884 |
| U021 | Lukelele | 2021-08-26 | https://stackoverflow.com/questions/68944794 |
| U022 | rafaelpadu | 2021-09-02 | https://stackoverflow.com/questions/69023142 |
| U023 | Jessin Ra | 2021-09-09 | https://stackoverflow.com/questions/69120036 |
| U024 | Raashid | 2021-09-09 | https://stackoverflow.com/questions/69122354 |
| U025 | Lavkant Kachhwaha | 2021-10-21 | https://stackoverflow.com/questions/69659951 |
| U026 | Docmaillou | 2021-10-27 | https://stackoverflow.com/questions/69740880 |
| U027 | Agr Acabdia | 2021-10-28 | https://stackoverflow.com/questions/69756439 |
| U028 | Jatin Mehrotra | 2021-10-29 | https://stackoverflow.com/questions/69768867 |
| U029 | otoo | 2021-10-29 | https://stackoverflow.com/questions/69771890 |
| U030 | Vibhor Gupta | 2021-10-29 | https://stackoverflow.com/questions/69774249 |
| U031 | user14370029 | 2021-11-01 | https://stackoverflow.com/questions/69802076 |
| U032 | dfmaaa1 | 2021-11-03 | https://stackoverflow.com/questions/69827293 |
| U033 | dbld | 2021-11-04 | https://stackoverflow.com/questions/69837030 |
| U034 | CHANDRU R | 2021-11-04 | https://stackoverflow.com/questions/69838701 |
| U035 | M&#225;rcio Mocellin | 2021-11-05 | https://stackoverflow.com/questions/69857248 |
| U036 | Oscar Cely | 2021-11-10 | https://stackoverflow.com/questions/69918631 |
| U037 | daniel ernest | 2021-11-13 | https://stackoverflow.com/questions/69954625 |
| U038 | J&#225;nos | 2021-11-17 | https://stackoverflow.com/questions/70009436 |
| U039 | Sjracvo Htrac | 2021-11-21 | https://stackoverflow.com/questions/70057979 |
| U040 | Bek | 2021-11-22 | https://stackoverflow.com/questions/70065121 |
| U041 | Valeri Buturishvili | 2021-11-23 | https://stackoverflow.com/questions/70083966 |
| U042 | Tim Richardson | 2021-12-01 | https://stackoverflow.com/questions/70179126 |
| U043 | RowSalmon | 2021-12-02 | https://stackoverflow.com/questions/70193935 |
| U044 | hackedXD | 2021-12-06 | https://stackoverflow.com/questions/70246342 |
| U045 | Zachiah | 2021-12-08 | https://stackoverflow.com/questions/70281879 |
| U046 | Flow | 2021-12-18 | https://stackoverflow.com/questions/70404428 |
| U047 | SSubedi | 2021-12-19 | https://stackoverflow.com/questions/70408917 |
| U048 | Abraham | 2021-12-20 | https://stackoverflow.com/questions/70428218 |
| U049 | Abraham | 2022-01-02 | https://stackoverflow.com/questions/70559637 |
| U050 | Gustavo M&#225;ximo | 2022-01-03 | https://stackoverflow.com/questions/70567353 |
| U051 | Yosri Mhamdi | 2022-01-07 | https://stackoverflow.com/questions/70627935 |
| U052 | Stef1611 | 2022-01-20 | https://stackoverflow.com/questions/70783731 |
| U053 | Kushagra | 2022-01-21 | https://stackoverflow.com/questions/70800167 |
| U054 | ThrowsError | 2022-01-23 | https://stackoverflow.com/questions/70822687 |
| U055 | Yulian | 2022-01-27 | https://stackoverflow.com/questions/70873622 |
| U056 | Iconejey | 2022-02-02 | https://stackoverflow.com/questions/70959002 |
| U057 | Jacob Valdez | 2022-02-03 | https://stackoverflow.com/questions/70965751 |
| U058 | Maybe Lindow | 2022-02-05 | https://stackoverflow.com/questions/70995718 |
| U059 | Kongpop Parkpisas | 2022-02-06 | https://stackoverflow.com/questions/71007828 |
| U060 | HyperText Markup Man | 2022-02-17 | https://stackoverflow.com/questions/71152461 |
| U061 | Vu Khai Hoan | 2022-02-18 | https://stackoverflow.com/questions/71167974 |
| U062 | Jeff Ward | 2022-02-22 | https://stackoverflow.com/questions/71224911 |
| U063 | Sheshank Garrepalli | 2022-03-01 | https://stackoverflow.com/questions/71312074 |
| U064 | saurav tripathi | 2022-03-04 | https://stackoverflow.com/questions/71352201 |
| U065 | Spandan Roy | 2022-03-05 | https://stackoverflow.com/questions/71362661 |
| U066 | Mateus  | 2022-03-06 | https://stackoverflow.com/questions/71367058 |
| U067 | Samil Kahraman | 2022-03-07 | https://stackoverflow.com/questions/71378997 |
| U068 | ProtoTurquie | 2022-03-07 | https://stackoverflow.com/questions/71382903 |
| U069 | Anh Tuấn Nguyễn | 2022-03-17 | https://stackoverflow.com/questions/71508274 |
| U070 | CanineData | 2022-03-29 | https://stackoverflow.com/questions/71665751 |
| U071 | JPSpronsniper Sniper | 2022-03-29 | https://stackoverflow.com/questions/71668765 |
| U072 | Mahendra  | 2022-04-01 | https://stackoverflow.com/questions/71702171 |
| U073 | Quico Llinares Llorens | 2022-04-06 | https://stackoverflow.com/questions/71766744 |
| U074 | Arnish B | 2022-04-09 | https://stackoverflow.com/questions/71806576 |
| U075 | Naikho | 2022-04-09 | https://stackoverflow.com/questions/71807157 |
| U076 | linka | 2022-04-10 | https://stackoverflow.com/questions/71818580 |
| U077 | Micael Jarniac | 2022-04-11 | https://stackoverflow.com/questions/71834183 |
| U078 | Medallyon | 2022-04-12 | https://stackoverflow.com/questions/71848842 |
| U079 | Rhyez | 2022-04-16 | https://stackoverflow.com/questions/71894664 |
| U080 | Nothing here | 2022-04-17 | https://stackoverflow.com/questions/71905508 |
| U081 | Wilhelmo Gutred | 2022-04-25 | https://stackoverflow.com/questions/71993339 |
| U082 | bonum_cete | 2022-04-29 | https://stackoverflow.com/questions/72064329 |
| U083 | Newbie007 | 2022-05-05 | https://stackoverflow.com/questions/72130766 |
| U084 | xezo360hye | 2022-05-09 | https://stackoverflow.com/questions/72174839 |
| U085 | Nothing here | 2022-05-11 | https://stackoverflow.com/questions/72206362 |
| U086 | Siegfried | 2022-05-11 | https://stackoverflow.com/questions/72207701 |
| U087 | Jake Horban | 2022-05-12 | https://stackoverflow.com/questions/72222950 |
| U088 | Impulsleistung | 2022-05-13 | https://stackoverflow.com/questions/72228174 |
| U089 | Marlon | 2022-05-13 | https://stackoverflow.com/questions/72234717 |
| U090 | BlueFalconHD | 2022-05-18 | https://stackoverflow.com/questions/72282605 |
| U091 | N&#237;colas Franzolin | 2022-05-19 | https://stackoverflow.com/questions/72311242 |
| U092 | 1euro7cent | 2022-05-22 | https://stackoverflow.com/questions/72336936 |
| U093 | Evgeniy | 2022-06-01 | https://stackoverflow.com/questions/72456344 |
| U094 | 曹培胜 | 2022-06-05 | https://stackoverflow.com/questions/72505280 |
| U095 | DanielB | 2022-06-07 | https://stackoverflow.com/questions/72529618 |
| U096 | Andre.L | 2022-06-07 | https://stackoverflow.com/questions/72537148 |
| U097 | Exploring | 2022-06-09 | https://stackoverflow.com/questions/72554328 |
| U098 | רועי סלע | 2022-06-09 | https://stackoverflow.com/questions/72562648 |
| U099 | Sparcyx | 2022-06-10 | https://stackoverflow.com/questions/72571613 |
| U100 | yoKurt | 2022-06-13 | https://stackoverflow.com/questions/72600079 |
| U101 | Jo Liss | 2022-06-14 | https://stackoverflow.com/questions/72617988 |
| U102 | coderWZL | 2022-06-16 | https://stackoverflow.com/questions/72643259 |
| U103 | Plaul | 2022-06-17 | https://stackoverflow.com/questions/72656062 |
| U104 | Alberto Carraro | 2022-06-17 | https://stackoverflow.com/questions/72664871 |
| U105 | Louis Lecouturier | 2022-06-22 | https://stackoverflow.com/questions/72713852 |
| U106 | Zebratic | 2022-06-25 | https://stackoverflow.com/questions/72750893 |
| U107 | Louis Ingenthron | 2022-06-30 | https://stackoverflow.com/questions/72809236 |
| U108 | Mordor1110 | 2022-07-01 | https://stackoverflow.com/questions/72828223 |
| U109 | stevec | 2022-07-06 | https://stackoverflow.com/questions/72877008 |
| U110 | beatrice zmau | 2022-07-08 | https://stackoverflow.com/questions/72911525 |
| U111 | Maximilian Jesch | 2022-07-13 | https://stackoverflow.com/questions/72966174 |
| U112 | vexliva | 2022-07-17 | https://stackoverflow.com/questions/73010768 |
| U113 | Saul Mu&#241;oz Garcia | 2022-07-18 | https://stackoverflow.com/questions/73028823 |
| U114 | true_mogician | 2022-07-20 | https://stackoverflow.com/questions/73056354 |
| U115 | aaportel | 2022-07-20 | https://stackoverflow.com/questions/73056498 |
| U116 | TedTran2019 | 2022-07-22 | https://stackoverflow.com/questions/73075410 |
| U117 | Irina Rapoport | 2022-07-30 | https://stackoverflow.com/questions/73177936 |
| U118 | Exploring | 2022-08-04 | https://stackoverflow.com/questions/73242748 |
| U119 | Pedro Braz | 2022-08-05 | https://stackoverflow.com/questions/73255193 |
| U120 | Bar Akiva | 2022-08-10 | https://stackoverflow.com/questions/73303215 |
| U121 | Elin_Rv0 | 2022-08-20 | https://stackoverflow.com/questions/73427693 |
| U122 | Miguel Gargallo | 2022-08-23 | https://stackoverflow.com/questions/73464324 |
| U123 | Toastlover | 2022-08-26 | https://stackoverflow.com/questions/73497320 |
| U124 | Ivory | 2022-08-26 | https://stackoverflow.com/questions/73506687 |
| U125 | NoobMaster_69 | 2022-09-04 | https://stackoverflow.com/questions/73602090 |
| U126 | thewebtud | 2022-09-07 | https://stackoverflow.com/questions/73639787 |
| U127 | Pirax | 2022-09-08 | https://stackoverflow.com/questions/73647046 |
| U128 | John Kears | 2022-09-11 | https://stackoverflow.com/questions/73682173 |
| U129 | GorvGoyl | 2022-09-13 | https://stackoverflow.com/questions/73705091 |
| U130 | Esqarrouth | 2022-09-13 | https://stackoverflow.com/questions/73709862 |
| U131 | Rickhomes | 2022-09-14 | https://stackoverflow.com/questions/73715053 |
| U132 | Mel | 2022-09-17 | https://stackoverflow.com/questions/73751606 |
| U133 | bonaparten | 2022-09-20 | https://stackoverflow.com/questions/73792971 |
| U134 | Chilusoft | 2022-09-23 | https://stackoverflow.com/questions/73827540 |
| U135 | Ocean Overflow | 2022-09-25 | https://stackoverflow.com/questions/73848372 |
| U136 | null_user | 2022-09-28 | https://stackoverflow.com/questions/73879649 |
| U137 | Shlomi Hassid | 2022-10-09 | https://stackoverflow.com/questions/74008676 |
| U138 | hanshenrik | 2022-10-13 | https://stackoverflow.com/questions/74053250 |
| U139 | John | 2022-10-17 | https://stackoverflow.com/questions/74091857 |
| U140 | Taliesin | 2022-10-18 | https://stackoverflow.com/questions/74110399 |
| U141 | user12461763 | 2022-10-25 | https://stackoverflow.com/questions/74198524 |
| U142 | Paul | 2022-10-26 | https://stackoverflow.com/questions/74213723 |
| U143 | mortenma71 | 2022-11-05 | https://stackoverflow.com/questions/74326142 |
| U144 | Kirk Ouimet | 2022-11-05 | https://stackoverflow.com/questions/74329830 |
| U145 | art vanderlay | 2022-11-09 | https://stackoverflow.com/questions/74373928 |
| U146 | c.leblanc | 2022-11-11 | https://stackoverflow.com/questions/74396836 |
| U147 | Foobar | 2022-11-14 | https://stackoverflow.com/questions/74425998 |
| U148 | Ramazan | 2022-11-20 | https://stackoverflow.com/questions/74511049 |
| U149 | user20660199 | 2022-12-01 | https://stackoverflow.com/questions/74648097 |
| U150 | Mel | 2022-12-02 | https://stackoverflow.com/questions/74652182 |
| U151 | LP_Cong | 2022-12-06 | https://stackoverflow.com/questions/74700585 |
| U152 | Hlintony H | 2022-12-10 | https://stackoverflow.com/questions/74751935 |
| U153 | Danylo Liakhovetskyi | 2022-12-12 | https://stackoverflow.com/questions/74772185 |
| U154 | hedgedandlevered | 2022-12-12 | https://stackoverflow.com/questions/74777697 |
| U155 | Nahuel | 2022-12-14 | https://stackoverflow.com/questions/74792689 |
| U156 | Rajesh Kanna | 2022-12-14 | https://stackoverflow.com/questions/74792936 |
| U157 | Alex Mortez | 2022-12-14 | https://stackoverflow.com/questions/74793102 |
| U158 | RubenNeves | 2022-12-17 | https://stackoverflow.com/questions/74831414 |
| U159 | John James | 2022-12-17 | https://stackoverflow.com/questions/74831509 |
| U160 | Katelynn Crick | 2022-12-17 | https://stackoverflow.com/questions/74831720 |
| U161 | Thomas David Kehoe | 2022-12-19 | https://stackoverflow.com/questions/74845965 |
| U162 | Hao Yuan | 2022-12-20 | https://stackoverflow.com/questions/74865401 |
| U163 | elksie5000 | 2022-12-23 | https://stackoverflow.com/questions/74900603 |
| U164 | dddictionary | 2023-01-07 | https://stackoverflow.com/questions/75037959 |
| U165 | kan niet anders | 2023-01-11 | https://stackoverflow.com/questions/75085854 |
| U166 | Jacob Stern | 2023-01-13 | https://stackoverflow.com/questions/75114315 |
| U167 | Helen | 2023-01-16 | https://stackoverflow.com/questions/75129990 |
| U168 | giorgi | 2023-01-18 | https://stackoverflow.com/questions/75165147 |
| U169 | Manolo | 2023-01-20 | https://stackoverflow.com/questions/75183662 |
| U170 | dakioso | 2023-01-23 | https://stackoverflow.com/questions/75207730 |
| U171 | Diego | 2023-01-23 | https://stackoverflow.com/questions/75213752 |
| U172 | H4B1TZ | 2023-01-24 | https://stackoverflow.com/questions/75216866 |
| U173 | Sanjai R | 2023-01-26 | https://stackoverflow.com/questions/75248130 |
| U174 | BrainPermafrost | 2023-01-26 | https://stackoverflow.com/questions/75250790 |
| U175 | Syed M Abbas Haider Taqvi | 2023-01-29 | https://stackoverflow.com/questions/75274341 |
| U176 | owen | 2023-01-29 | https://stackoverflow.com/questions/75276040 |
| U177 | Gary | 2023-02-01 | https://stackoverflow.com/questions/75305297 |
| U178 | ale_lo | 2023-02-04 | https://stackoverflow.com/questions/75348164 |
| U179 | Rohring Rook | 2023-02-07 | https://stackoverflow.com/questions/75377406 |
| U180 | Pamela Fox | 2023-02-07 | https://stackoverflow.com/questions/75380181 |
| U181 | Lee McAlilly | 2023-02-08 | https://stackoverflow.com/questions/75392395 |
| U182 | Coding With Toms | 2023-02-20 | https://stackoverflow.com/questions/75507156 |
| U183 | kaan_atakan | 2023-02-20 | https://stackoverflow.com/questions/75512032 |
| U184 | Diego | 2023-02-24 | https://stackoverflow.com/questions/75553667 |
| U185 | Etiennel | 2023-02-24 | https://stackoverflow.com/questions/75554835 |
| U186 | William Entriken | 2023-03-01 | https://stackoverflow.com/questions/75600002 |
| U187 | iconoclast | 2023-03-01 | https://stackoverflow.com/questions/75609269 |
| U188 | brohjoe | 2023-03-02 | https://stackoverflow.com/questions/75610875 |
| U189 | Ahmad | 2023-03-03 | https://stackoverflow.com/questions/75624961 |
| U190 | RDK | 2023-03-06 | https://stackoverflow.com/questions/75655376 |
| U191 | thewb | 2023-03-09 | https://stackoverflow.com/questions/75688720 |
| U192 | L K | 2023-03-09 | https://stackoverflow.com/questions/75689253 |
| U193 | bhushan laware | 2023-03-11 | https://stackoverflow.com/questions/75707565 |
| U194 | dnrandom | 2023-03-12 | https://stackoverflow.com/questions/75715006 |
| U195 | walkman | 2023-03-13 | https://stackoverflow.com/questions/75721009 |
| U196 | Grismar | 2023-03-14 | https://stackoverflow.com/questions/75728582 |
| U197 | David Thielen | 2023-03-15 | https://stackoverflow.com/questions/75748806 |
| U198 | Ian | 2023-03-19 | https://stackoverflow.com/questions/75785497 |
| U199 | Grant Curell | 2023-03-21 | https://stackoverflow.com/questions/75802296 |
| U200 | Kyryl Zotov | 2023-03-22 | https://stackoverflow.com/questions/75810769 |
| U201 | Steve | 2023-03-22 | https://stackoverflow.com/questions/75817726 |
| U202 | Vey | 2023-03-23 | https://stackoverflow.com/questions/75821602 |
| U203 | Thomas Sch&#228;tzing | 2023-03-23 | https://stackoverflow.com/questions/75827616 |
| U204 | Pierce Harris | 2023-03-24 | https://stackoverflow.com/questions/75831120 |
| U205 | Oliver Olss&#233;n | 2023-03-24 | https://stackoverflow.com/questions/75835737 |
| U206 | hanugm | 2023-03-25 | https://stackoverflow.com/questions/75843776 |
| U207 | Krzysztof Romańczuk | 2023-03-26 | https://stackoverflow.com/questions/75850775 |
| U208 | Nikhil REDDY | 2023-03-27 | https://stackoverflow.com/questions/75859757 |
| U209 | Yamin Siahmargooei | 2023-03-28 | https://stackoverflow.com/questions/75861922 |
| U210 | user21535488 | 2023-03-31 | https://stackoverflow.com/questions/75898544 |
| U211 | Donaaal | 2023-04-01 | https://stackoverflow.com/questions/75904268 |
| U212 | Matthew Walton | 2023-04-03 | https://stackoverflow.com/questions/75916008 |
| U213 | Natalionaire | 2023-04-03 | https://stackoverflow.com/questions/75922278 |
| U214 | Laurent Claessens | 2023-04-04 | https://stackoverflow.com/questions/75926959 |
| U215 | Gin Quin | 2023-04-06 | https://stackoverflow.com/questions/75947827 |
| U216 | Kevin Weinrich | 2023-04-11 | https://stackoverflow.com/questions/75990864 |
| U217 | khateeb | 2023-04-12 | https://stackoverflow.com/questions/75992507 |
| U218 | tonetone | 2023-04-13 | https://stackoverflow.com/questions/76007592 |
| U219 | JasonC | 2023-04-13 | https://stackoverflow.com/questions/76009072 |
| U220 | dafna | 2023-04-14 | https://stackoverflow.com/questions/76016049 |
| U221 | JamesC | 2023-04-14 | https://stackoverflow.com/questions/76017165 |
| U222 | jun c | 2023-04-17 | https://stackoverflow.com/questions/76036793 |
| U223 | William Entriken | 2023-04-17 | https://stackoverflow.com/questions/76037936 |
| U224 | Vaibhav Bhardwaj | 2023-04-19 | https://stackoverflow.com/questions/76058788 |
| U225 | Ofer Gal | 2023-04-21 | https://stackoverflow.com/questions/76070342 |
| U226 | Christopher Hall | 2023-04-21 | https://stackoverflow.com/questions/76072219 |
| U227 | giulioBorriello | 2023-04-21 | https://stackoverflow.com/questions/76073108 |
| U228 | whonkg985 | 2023-04-21 | https://stackoverflow.com/questions/76075204 |
| U229 | Patrick | 2023-05-01 | https://stackoverflow.com/questions/76147937 |
| U230 | Alex_X1 | 2023-05-03 | https://stackoverflow.com/questions/76162353 |
| U231 | Sherif Elmetainy | 2023-05-04 | https://stackoverflow.com/questions/76177140 |
| U232 | Michele | 2023-05-10 | https://stackoverflow.com/questions/76220144 |
| U233 | Leo | 2023-05-11 | https://stackoverflow.com/questions/76230446 |
| U234 | Gabriel Ciubotaru | 2023-05-12 | https://stackoverflow.com/questions/76234921 |
| U235 | Omar | 2023-05-13 | https://stackoverflow.com/questions/76243327 |
| U236 | mhm.sherpa | 2023-05-15 | https://stackoverflow.com/questions/76256774 |
| U237 | Sterling | 2023-05-15 | https://stackoverflow.com/questions/76257401 |
| U238 | BKDziti | 2023-05-16 | https://stackoverflow.com/questions/76266095 |
| U239 | user2458046 | 2023-05-16 | https://stackoverflow.com/questions/76266140 |
| U240 | Corram | 2023-05-17 | https://stackoverflow.com/questions/76269633 |
| U241 | cosmos | 2023-05-22 | https://stackoverflow.com/questions/76310342 |
| U242 | Joel Hager | 2023-05-23 | https://stackoverflow.com/questions/76311798 |
| U243 | esege | 2023-05-24 | https://stackoverflow.com/questions/76324985 |
| U244 | Simon Suh | 2023-05-26 | https://stackoverflow.com/questions/76344685 |
| U245 | Arman Asgharpoor | 2023-05-27 | https://stackoverflow.com/questions/76349255 |
| U246 | Producdevity | 2023-05-28 | https://stackoverflow.com/questions/76349751 |
| U247 | HRNPH | 2023-05-29 | https://stackoverflow.com/questions/76357695 |
| U248 | Kris van der Mast | 2023-06-01 | https://stackoverflow.com/questions/76384230 |
| U249 | dnAir | 2023-06-03 | https://stackoverflow.com/questions/76396755 |
| U250 | badmood111 | 2023-06-06 | https://stackoverflow.com/questions/76417192 |
| U251 | Sami.C | 2023-06-09 | https://stackoverflow.com/questions/76436635 |
| U252 | Jeff Neet | 2023-06-10 | https://stackoverflow.com/questions/76444491 |
| U253 | Doug | 2023-06-11 | https://stackoverflow.com/questions/76448780 |
| U254 | Tom | 2023-06-11 | https://stackoverflow.com/questions/76452744 |
| U255 | Daniel Barnes | 2023-06-16 | https://stackoverflow.com/questions/76486363 |
| U256 | Laurens | 2023-06-16 | https://stackoverflow.com/questions/76488726 |
