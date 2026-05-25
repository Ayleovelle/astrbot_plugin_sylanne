# 机器学习 OpenAlex 文献元数据 full 第 34 卷

- 范围：第 16501 到 17000 条
- 方向：机器学习（Machine Learning）
- 分组：AI/计算机
- 语料类型：full
- 用途：文献综述线索、研究主题定位、关键词扩展、代表性论文检索。
- 注意：本卷不是论文全文库，不能替代正式阅读和引用核验。

## 16501. Sample Complexity of Asynchronous Q-Learning: Sharper Analysis and Variance Reduction

- 标题：Sample Complexity of Asynchronous Q-Learning: Sharper Analysis and Variance Reduction
- 作者：Gen Li, Yuting Wei, Yuejie Chi, Yuantao Gu, Yuxin Chen
- 年份：2021
- 出版日期：2021-10-15
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1109/tit.2021.3120096
- OpenAlex ID：https://openalex.org/W3034039613
- 落地页：https://doi.org/10.1109/tit.2021.3120096
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/18/9660615/09570295.pdf
- 主主题：Reinforcement Learning in Robotics
- 主题：Reinforcement Learning in Robotics, Machine Learning and Algorithms, Quantum many-body systems
- 关键词：Combinatorics, Mathematics, Upper and lower bounds, Sample complexity, Distribution (mathematics), Logarithm, Discrete mathematics, State (computer science), Scaling, Mathematical analysis, Algorithm, Computer science, Geometry
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Asynchronous Q-learning aims to learn the optimal action-value function (or Q-function) of a Markov decision process (MDP), based on a single trajectory of Markovian samples induced by a behavior policy. Focusing on a <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\gamma $ </tex-math></inline-formula> -discounted MDP with state space <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\mathcal {S}$ </tex-math></inline-formula> and action space <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\mathcal {A}$ </tex-math></inline-formula> , we demonstrate that the <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\ell _{\infty }$ </tex-math></inline-formula> -based sample complexity of classical asynchronous Q-learning — namely, the number of samples needed to yield an entrywise <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\varepsilon $ </tex-math></inline-formula> -accurate estimate of the Q-function — is at most on the order of <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\frac {1}{ \mu _{\mathsf {min}}(1-\gamma)^{5}\varepsilon ^{2}}+ \frac { t_{\mathsf {mix}}}{ \mu _{\mathsf {min}}(1-\gamma)}$ </tex-math></inline-formula> up to some logarithmic factor, provided that a proper constant learning rate is adopted. Here, <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$t_{\mathsf {mix}}$ </tex-math></inline-formula> and <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\mu _{\mathsf {min}}$ </tex-math></inline-formula> denote respectively the mixing time and the minimum state-action occupancy probability of the sample trajectory. The first term of this bound matches the sample complexity in the synchronous case with independent samples drawn from the stationary distribution of the trajectory. The second term reflects the cost taken for the empirical distribution of the Markovian trajectory to reach a steady state, which is incurred at the very beginning and becomes amortized as the algorithm runs. Encouragingly, the above bound improves upon the state-of-the-art result by a factor of at least <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$|\mathcal {S}||\mathcal {A}|$ </tex-math></inline-formula> for all scenarios, and by a factor of at least <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$t_{\mathsf {mix}}|\mathcal {S}||\mathcal {A}|$ </tex-math></inline-formula> for any sufficiently small accuracy level <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\varepsilon $ </tex-math></inline-formula> . Further, we demonstrate that the scaling on the effective horizon <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$\frac {1}{1-\gamma }$ </tex-math></inline-formula> can be improved by means of variance reduction.

## 16502. Policy Iteration for Linear Quadratic Games With Stochastic Parameters

- 标题：Policy Iteration for Linear Quadratic Games With Stochastic Parameters
- 作者：Benjamin Gravell, Karthik Ganapathy, Tyler Summers
- 年份：2020
- 出版日期：2020-06-11
- 类型：article
- 语言：en
- 来源：IEEE Control Systems Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2475-1456
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/lcsys.2020.3001883
- OpenAlex ID：https://openalex.org/W3034247939
- 落地页：https://doi.org/10.1109/lcsys.2020.3001883
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Reinforcement Learning in Robotics, Adaptive Dynamic Programming Control
- 关键词：Robustness (evolution), Computer science, Mathematical optimization, Adversarial system, Artificial intelligence, Robotics, Game theory, Quadratic equation, Machine learning, Theoretical computer science, Robot, Mathematics, Mathematical economics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Robustness is a key challenge in the integration of learning and control. In machine learning and robotics, two common approaches to promote robustness are adversarial training and domain randomization. Both of these approaches have analogs in control theory: adversarial training relates to H <sub xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">∞</sub> control and dynamic game theory, while domain randomization relates to theory for systems with stochastic model parameters. We propose a stochastic dynamic game framework that integrates both of these complementary approaches to modeling uncertainty and promoting robustness. We describe policy iteration algorithms in both model-based and model-free settings to compute equilibrium strategies and value functions. We present numerical experiments that illustrate their effectiveness and the value of combining uncertainty representations in our integrated framework. We also provide an open-source implementation of the algorithms to facilitate their wider use.

## 16503. Multi-component transfer metric learning for handling unrelated source domain samples

- 标题：Multi-component transfer metric learning for handling unrelated source domain samples
- 作者：Chang’an Yi, Yonghui Xu, Han Yu, Yuguang Yan, Yang Liu
- 年份：2020
- 出版日期：2020-06-12
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2020.106132
- OpenAlex ID：https://openalex.org/W3034461381
- 落地页：https://doi.org/10.1016/j.knosys.2020.106132
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Human Pose and Action Recognition
- 关键词：Metric (unit), Transfer of learning, Computer science, Mahalanobis distance, Component (thermodynamics), Machine learning, Artificial intelligence, Domain (mathematical analysis), Overhead (engineering), Negative transfer, Transfer (computing), Sample (material), Component analysis, Data mining, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16504. A text-based visual context modulation neural model for multimodal machine translation

- 标题：A text-based visual context modulation neural model for multimodal machine translation
- 作者：Soonmo Kwon, Byung-Hyun Go, Jong-Hyeok Lee
- 年份：2020
- 出版日期：2020-06-15
- 类型：article
- 语言：en
- 来源：Pattern Recognition Letters
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-8655
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patrec.2020.06.010
- OpenAlex ID：https://openalex.org/W3035421790
- 落地页：https://doi.org/10.1016/j.patrec.2020.06.010
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Natural Language Processing Techniques, Topic Modeling
- 关键词：Computer science, Machine translation, Artificial intelligence, Transformer, Feature (linguistics), Modular design, Translation (biology), Encoder, Pattern recognition (psychology), Speech recognition, Natural language processing, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16505. Towards Automatic Skeleton Extraction With Skeleton Grafting

- 标题：Towards Automatic Skeleton Extraction With Skeleton Grafting
- 作者：Cong Yang, Bipin Indurkhya, John See, Marcin Grzegorzek
- 年份：2020
- 出版日期：2020-06-22
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Visualization and Computer Graphics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1077-2626
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tvcg.2020.3003994
- OpenAlex ID：https://openalex.org/W3035939744
- 落地页：https://doi.org/10.1109/tvcg.2020.3003994
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications
- 关键词：Skeleton (computer programming), Topological skeleton, Computer science, Matching (statistics), Artificial intelligence, Smoothing, Pruning, Computer vision, Pattern recognition (psychology), Segmentation, Mathematics, Active shape model
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This article introduces a novel approach to generate visually promising skeletons automatically without any manual tuning. In practice, it is challenging to extract promising skeletons directly using existing approaches. This is because they either cannot fully preserve shape features, or require manual intervention, such as boundary smoothing and skeleton pruning, to justify the eye-level view assumption. We propose an approach here that generates backbone and dense skeletons by shape input, and then extends the backbone branches via skeleton grafting from the dense skeleton to ensure a well-integrated output. Based on our evaluation, the generated skeletons best depict the shapes at levels that are similar to human perception. To evaluate and fully express the properties of the extracted skeletons, we introduce two potential functions within the high-order matching protocol to improve the accuracy of skeleton-based matching. These two functions fuse the similarities between skeleton graphs and geometrical relations characterized by multiple skeleton endpoints. Experiments on three high-order matching protocols show that the proposed potential functions can effectively reduce the number of incorrect matches.

## 16506. Reproducible and Efficient Benchmarks for Hyperparameter Optimization of Neural Machine Translation Systems

- 标题：Reproducible and Efficient Benchmarks for Hyperparameter Optimization of Neural Machine Translation Systems
- 作者：Xuan Zhang, Kevin Duh
- 年份：2020
- 出版日期：2020-07-20
- 类型：article
- 语言：en
- 来源：Transactions of the Association for Computational Linguistics
- 来源类型：journal
- 出版方：Association for Computational Linguistics
- ISSN-L：2307-387X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1162/tacl_a_00322
- OpenAlex ID：https://openalex.org/W3044285325
- 落地页：https://doi.org/10.1162/tacl_a_00322
- 开放 PDF 链接：https://direct.mit.edu/tacl/article-pdf/doi/10.1162/tacl_a_00322/1923686/tacl_a_00322.pdf
- 主主题：Advanced Multi-Objective Optimization Algorithms
- 主题：Advanced Multi-Objective Optimization Algorithms, Machine Learning and Data Classification, Metaheuristic Optimization Algorithms Research
- 关键词：Hyperparameter, Computer science, Machine translation, Machine learning, Benchmark (surveying), Artificial intelligence, Artificial neural network, Range (aeronautics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Hyperparameter selection is a crucial part of building neural machine translation (NMT) systems across both academia and industry. Fine-grained adjustments to a model’s architecture or training recipe can mean the difference between a positive and negative research result or between a state-of-the-art and underperforming system. While recent literature has proposed methods for automatic hyperparameter optimization (HPO), there has been limited work on applying these methods to neural machine translation (NMT), due in part to the high costs associated with experiments that train large numbers of model variants. To facilitate research in this space, we introduce a lookup-based approach that uses a library of pre-trained models for fast, low cost HPO experimentation. Our contributions include (1) the release of a large collection of trained NMT models covering a wide range of hyperparameters, (2) the proposal of targeted metrics for evaluating HPO methods on NMT, and (3) a reproducible benchmark of several HPO methods against our model library, including novel graph-based and multiobjective methods.

## 16507. A Novel Class Noise Detection Method for High-Dimensional Data in Industrial Informatics

- 标题：A Novel Class Noise Detection Method for High-Dimensional Data in Industrial Informatics
- 作者：Donghai Guan, Kai Chen, Guangjie Han, Shuqiang Huang, Weiwei Yuan, Mohsen Guizani, Lei Shu
- 年份：2020
- 出版日期：2020-07-29
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Industrial Informatics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1551-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tii.2020.3012658
- OpenAlex ID：https://openalex.org/W3046705914
- 落地页：https://doi.org/10.1109/tii.2020.3012658
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Industrial Vision Systems and Defect Detection, Imbalanced Data Classification Techniques
- 关键词：Computer science, Noise (video), Feature selection, Artificial intelligence, Pattern recognition (psychology), Noise measurement, Curse of dimensionality, Machine learning, Feature (linguistics), Benchmark (surveying), Ensemble learning, Subspace topology, Data mining, Filter (signal processing), Noise reduction, Computer vision
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The data in industrial informatics may be high-dimensional and mislabeled. Irrelevant or noisy features pose a significant challenge to the detection of high-dimensional mislabeling. The traditional method usually adopts a two-step solution, first finding the relevant subspace and then using it for mislabeling detection. This two-step method struggles to provide the optimal mislabeling detection performance, since it separates the procedures of feature selection and label error detection. To solve this problem, in this article, we integrate the two steps and propose a sequential ensemble noise filter (SENF). In the SENF, relevant features are selected and used to generate a noise score for each instance. Continuously, these noise scores guide feature selection in the regression learning. Thus, the SENF falls in the scope of sequential ensemble learning. We evaluate our approach on several benchmark datasets with high dimensionality and much label noise. It is shown that the SENF is significantly better than other existing label noise detection methods.

## 16508. Robust CAPTCHAs Towards Malicious OCR

- 标题：Robust CAPTCHAs Towards Malicious OCR
- 作者：Jiaming Zhang, Jitao Sang, Kaiyuan Xu, Shangxi Wu, Xian Zhao, Yanfeng Sun, Yongli Hu, Jian Yu
- 年份：2020
- 出版日期：2020-08-04
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2020.3013376
- OpenAlex ID：https://openalex.org/W3046953693
- 落地页：https://doi.org/10.1109/tmm.2020.3013376
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Digital Media Forensic Detection, Advanced Malware Detection Techniques
- 关键词：CAPTCHA, Turing test, Computer science, Adversarial system, Artificial intelligence, Context (archaeology), Machine learning, Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Turing test was originally proposed to examine whether machine's behavior is indistinguishable from a human. The most popular and practical Turing test is CAPTCHA, which is to discriminate algorithm from human by offering recognition-alike questions. The recent development of deep learning has significantly advanced the capability of algorithm in solving CAPTCHA questions, forcing CAPTCHA designers to increase question complexity. Instead of designing questions difficult for both algorithm and human, this study attempts to employ the limitations of algorithm to design robust CAPTCHA questions easily solvable to human. Specifically, our data analysis observes that human and algorithm demonstrates different vulnerability to visual distortions: adversarial perturbation is significantly annoying to algorithm yet friendly to human. We are motivated to employ adversarially perturbed images for robust CAPTCHA design in the context of character-based questions. Four modules of multi-target attack, ensemble adversarial training, image preprocessing differentiable approximation, and expectation are proposed to address the characteristics of character-based CAPTCHA cracking. Qualitative and quantitative experimental results demonstrate the effectiveness of the proposed solution. We hope this study can lead to the discussions around adversarial attack/defense in CAPTCHA design and also inspire the future attempts in employing algorithm limitation for practical usage.

## 16509. Improving Image Description with Auxiliary Modality for Visual Localization in Challenging Conditions

- 标题：Improving Image Description with Auxiliary Modality for Visual Localization in Challenging Conditions
- 作者：Nathan Piasco, Désiré Sidibé, Valérie Gouet-Brunet, Cédric Demonceaux
- 年份：2020
- 出版日期：2020-08-28
- 类型：article
- 语言：en
- 来源：International Journal of Computer Vision
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0920-5691
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11263-020-01363-6
- OpenAlex ID：https://openalex.org/W3048262413
- 落地页：https://doi.org/10.1007/s11263-020-01363-6
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Robotics and Sensor-Based Localization, Multimodal Machine Learning Applications
- 关键词：Artificial intelligence, Computer vision, Leverage (statistics), Computer science, Discriminative model, Key (lock), Search engine indexing, Modality (human–computer interaction), Matching (statistics), Simultaneous localization and mapping, Image (mathematics), Pattern recognition (psychology), Robot, Mobile robot, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16510. Multi-source domain adaptation with graph embedding and adaptive label prediction

- 标题：Multi-source domain adaptation with graph embedding and adaptive label prediction
- 作者：Ao Ma, Fuming You, Mengmeng Jing, Jingjing Li, Ke Lü
- 年份：2020
- 出版日期：2020-08-18
- 类型：article
- 语言：en
- 来源：Information Processing & Management
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0306-4573
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ipm.2020.102367
- OpenAlex ID：https://openalex.org/W3076174210
- 落地页：https://doi.org/10.1016/j.ipm.2020.102367
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Text and Document Classification Technologies, Multimodal Machine Learning Applications
- 关键词：Domain adaptation, Subspace topology, Computer science, Embedding, Domain (mathematical analysis), Similarity (geometry), Pattern recognition (psychology), Artificial intelligence, Graph, Multi-source, Algorithm, Machine learning, Data mining, Theoretical computer science, Mathematics, Statistics, Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16511. AI and ethics

- 标题：AI and ethics
- 作者：Susan Anderson, Michael Anderson
- 年份：2020
- 出版日期：2020-09-13
- 类型：article
- 语言：en
- 来源：AI and Ethics
- 来源类型：journal
- 出版方：Springer Nature
- ISSN-L：2730-5953
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1007/s43681-020-00003-6
- OpenAlex ID：https://openalex.org/W3085826631
- 落地页：https://doi.org/10.1007/s43681-020-00003-6
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s43681-020-00003-6.pdf
- 主主题：Ethics and Social Impacts of AI
- 主题：Ethics and Social Impacts of AI, Adversarial Robustness in Machine Learning, Neuroethics, Human Enhancement, Biomedical Innovations
- 关键词：Prima facie, Epistemology, Engineering ethics, Business ethics, Computer science, Sociology, Philosophy, Political science, Law, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16512. EI-MTD: Moving Target Defense for Edge Intelligence against Adversarial Attacks

- 标题：EI-MTD: Moving Target Defense for Edge Intelligence against Adversarial Attacks
- 作者：Yaguan Qian, Y.S. Guo, Qiqi Shao, Jiamin Wang, Bin Wang, Zhaoquan Gu, Xiang Ling, Chunming Wu
- 年份：2022
- 出版日期：2022-05-19
- 类型：article
- 语言：en
- 来源：ACM Transactions on Privacy and Security
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：2471-2566
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1145/3517806
- OpenAlex ID：https://openalex.org/W3087792431
- 落地页：https://doi.org/10.1145/3517806
- 开放 PDF 链接：https://dl.acm.org/doi/pdf/10.1145/3517806
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Privacy-Preserving Technologies in Data
- 关键词：Adversarial system, Computer science, Adversary, Computer security, Enhanced Data Rates for GSM Evolution, Cloud computing, Black box, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Edge intelligence has played an important role in constructing smart cities, but the vulnerability of edge nodes to adversarial attacks becomes an urgent problem. A so-called adversarial example can fool a deep learning model on an edge node for misclassification. Due to the transferability property of adversarial examples, an adversary can easily fool a black-box model by a local substitute model. Edge nodes in general have limited resources, which cannot afford a complicated defense mechanism like that on a cloud data center. To address the challenge, we propose a dynamic defense mechanism, namely EI-MTD. The mechanism first obtains robust member models of small size through differential knowledge distillation from a complicated teacher model on a cloud data center. Then, a dynamic scheduling policy, which builds on a Bayesian Stackelberg game, is applied to the choice of a target model for service. This dynamic defense mechanism can prohibit the adversary from selecting an optimal substitute model for black-box attacks. We also conduct extensive experiments to evaluate the proposed mechanism, and results show that EI-MTD could protect edge intelligence effectively against adversarial attacks in black-box settings.

## 16513. Balancing Exploration and Exploitation: A novel active learner for imbalanced data

- 标题：Balancing Exploration and Exploitation: A novel active learner for imbalanced data
- 作者：Alaa Tharwat, Wolfram Schenck
- 年份：2020
- 出版日期：2020-10-08
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2020.106500
- OpenAlex ID：https://openalex.org/W3092013197
- 落地页：https://doi.org/10.1016/j.knosys.2020.106500
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Imbalanced Data Classification Techniques, Algorithms and Data Compression
- 关键词：Computer science, Set (abstract data type), Active learning (machine learning), Selection (genetic algorithm), Machine learning, Annotation, Space (punctuation), Point (geometry), Artificial intelligence, Labeled data, Training set, Data mining, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16514. Robot Learning With Crash Constraints

- 标题：Robot Learning With Crash Constraints
- 作者：Alonso Marco, Dominik Baumann, Majid Khadiv, Philipp Hennig, Ludovic Righetti, Sebastian Trimpe
- 年份：2021
- 出版日期：2021-02-03
- 类型：article
- 语言：en
- 来源：IEEE Robotics and Automation Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2377-3766
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/lra.2021.3057055
- OpenAlex ID：https://openalex.org/W3093169645
- 落地页：https://doi.org/10.1109/lra.2021.3057055
- 主主题：Reinforcement Learning in Robotics
- 主题：Reinforcement Learning in Robotics, Advanced Bandit Algorithms Research, Machine Learning and Algorithms
- 关键词：Constraint (computer-aided design), Crash, Constraint learning, Robot, Control (management), Bayesian probability
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In the past decade, numerous machine learning algorithms have been shown to successfully learn optimal policies to control real robotic systems. However, it is common to encounter failing behaviors as the learning loop progresses. Specifically, in robot applications where failing is undesired but not catastrophic, many algorithms struggle with leveraging data obtained from failures. This is usually caused by (i) the failed experiment ending prematurely, or (ii) the acquired data being scarce or corrupted. Both complicate the design of proper reward functions to penalize failures. In this letter, we propose a framework that addresses those issues. We consider failing behaviors as those that violate a constraint and address the problem of learning with crash constraints, where no data is obtained upon constraint violation. The no-data case is addressed by a novel GP model (GPCR) for the constraint that combines discrete events (failure/success) with continuous observations (only obtained upon success). We demonstrate the effectiveness of our framework on simulated benchmarks and on a real jumping quadruped, where the constraint threshold is unknown a priori. Experimental data is collected, by means of constrained Bayesian optimization, directly on the real robot. Our results outperform manual tuning and GPCR proves useful on estimating the constraint threshold.

## 16515. Active Learning for Node Classification: An Evaluation

- 标题：Active Learning for Node Classification: An Evaluation
- 作者：Kaushalya Madhawa, Tsuyoshi Murata
- 年份：2020
- 出版日期：2020-10-16
- 类型：article
- 语言：en
- 来源：Entropy
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1099-4300
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/e22101164
- OpenAlex ID：https://openalex.org/W3093309692
- 落地页：https://doi.org/10.3390/e22101164
- 开放 PDF 链接：https://www.mdpi.com/1099-4300/22/10/1164/pdf?version=1603200760
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Advanced Graph Neural Networks, Topic Modeling
- 关键词：Computer science, Artificial intelligence, Machine learning, Hyperparameter, Artificial neural network, Graph, Deep learning, Labeled data, Benchmark (surveying), Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Current breakthroughs in the field of machine learning are fueled by the deployment of deep neural network models. Deep neural networks models are notorious for their dependence on large amounts of labeled data for training them. Active learning is being used as a solution to train classification models with less labeled instances by selecting only the most informative instances for labeling. This is especially important when the labeled data are scarce or the labeling process is expensive. In this paper, we study the application of active learning on attributed graphs. In this setting, the data instances are represented as nodes of an attributed graph. Graph neural networks achieve the current state-of-the-art classification performance on attributed graphs. The performance of graph neural networks relies on the careful tuning of their hyperparameters, usually performed using a validation set, an additional set of labeled instances. In label scarce problems, it is realistic to use all labeled instances for training the model. In this setting, we perform a fair comparison of the existing active learning algorithms proposed for graph neural networks as well as other data types such as images and text. With empirical results, we demonstrate that state-of-the-art active learning algorithms designed for other data types do not perform well on graph-structured data. We study the problem within the framework of the exploration-vs.-exploitation trade-off and propose a new count-based exploration term. With empirical evidence on multiple benchmark graphs, we highlight the importance of complementing uncertainty-based active learning models with an exploration term.

## 16516. Reweighting and information-guidance networks for Few-Shot Learning

- 标题：Reweighting and information-guidance networks for Few-Shot Learning
- 作者：Zhong Ji, Xingliang Chai, Yunlong Yu, Zhongfei Zhang
- 年份：2020
- 出版日期：2020-10-20
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2020.07.128
- OpenAlex ID：https://openalex.org/W3093670440
- 落地页：https://doi.org/10.1016/j.neucom.2020.07.128
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications
- 关键词：Computer science, Discriminative model, Representativeness heuristic, Benchmark (surveying), Artificial intelligence, Machine learning, ENCODE, Class (philosophy), Task (project management), Mechanism (biology), Shot (pellet), One shot, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16517. Video sketch: A middle-level representation for action recognition

- 标题：Video sketch: A middle-level representation for action recognition
- 作者：Xingyuan Zhang, Yaping Huang, Yang Mi, Yanting Pei, Qi Zou, Song Wang
- 年份：2020
- 出版日期：2020-11-06
- 类型：article
- 语言：en
- 来源：Applied Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0924-669X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10489-020-01905-y
- OpenAlex ID：https://openalex.org/W3095123887
- 落地页：https://doi.org/10.1007/s10489-020-01905-y
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Multimodal Machine Learning Applications, Hand Gesture Recognition Systems
- 关键词：Sketch, Computer science, Artificial intelligence, Modality (human–computer interaction), Representation (politics), Sketch recognition, Optical flow, RGB color model, Action recognition, Action (physics), Computer vision, Pattern recognition (psychology), Point (geometry), Motion (physics), Class (philosophy), Image (mathematics), Gesture recognition, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16518. Combining One-vs-One Decomposition and Instance-Based Learning for Multi-Class Classification

- 标题：Combining One-vs-One Decomposition and Instance-Based Learning for Multi-Class Classification
- 作者：Jun-Ying Liu, Bin-Bin Jia
- 年份：2020
- 出版日期：2020-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2020.3034448
- OpenAlex ID：https://openalex.org/W3096412097
- 落地页：https://doi.org/10.1109/access.2020.3034448
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/8948470/09241703.pdf
- 主主题：Text and Document Classification Technologies
- 主题：Text and Document Classification Technologies, Machine Learning and Data Classification, Imbalanced Data Classification Techniques
- 关键词：Computer science, Class (philosophy), Decomposition, Artificial intelligence, Machine learning, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Multi-class classification is one of the most important supervised learning problems and can be solved by either designing direct multi-class classifiers (direct strategy) or decomposing it into a set of binary classification problems (indirect strategy). Direct strategy only needs training one unified classifier while indirect strategy, especially the one-vs-one decomposition method, has shown its superiority and been utilized by some popular software packages. In this article, a first attempt towards bridging the gap between direct strategy and one-vs-one decomposition for multi-class classification is conducted, and accordingly a novel approach named CODIL is proposed. Specifically, CODIL firstly transforms the class vector into a ternary label matrix (only with {-1, 0, +1}) via one-vs-one rule, where each column of the label matrix corresponds to a pair of classes. Then, CODIL determines the binary label vector (only with {-1, +1}) for unseen instance by exploiting the manifold structure information residing in its k nearest neighbors, where each element of the label vector denotes the unseen instance's prediction for its corresponding class pair. Finally, the class for unseen instance is returned via majority voting based on the binary label vector. Extensive comparative studies are conducted between CODIL and six well-established multi-class approaches over seventeen benchmark multi-class data sets. The experimental results show the superiority of the proposed CODIL approach against the compared approaches.

## 16519. Image Classification Based on Automatic Neural Architecture Search Using Binary Crow Search Algorithm

- 标题：Image Classification Based on Automatic Neural Architecture Search Using Binary Crow Search Algorithm
- 作者：Mobeen Ahmad, Muhammad Abdullah, Hyeonjoon Moon, Seong Joon Yoo, Dongil Han
- 年份：2020
- 出版日期：2020-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2020.3031599
- OpenAlex ID：https://openalex.org/W3096898606
- 落地页：https://doi.org/10.1109/access.2020.3031599
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/8948470/09226534.pdf
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Video Surveillance and Tracking Methods, Machine Learning and Data Classification
- 关键词：Computer science, Artificial intelligence, Artificial neural network, Search algorithm, Metaheuristic, Pattern recognition (psychology), Genetic algorithm, Beam search, Machine learning, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Neural architectures have accelerated the advancement in various domains by enabling automatic pattern detection, image classification, audio recognition, and face recognition etc. However, they are computationally expensive to design and expert knowledge in various domains is required. In this paper, a swarm intelligence algorithm is proposed to search for novel architectures without human intervention that can achieve comparable performance to those of human-designed architectures. This work is inspired by current neural architecture search approaches based on reinforcement learning and genetic algorithm. However, not much attention is paid towards swarm intelligence metaheuristics-based neural architecture search. A framework is proposed for automatically designing neural architectures based on a swarm intelligence metaheuristic: Crow Search Algorithm. First, Crow Search Algorithm is integrated with binary network representation. To make it compatible for Neural Architecture Search, the original distance metric is replaced with hamming distance-based similarity measure. Second, the tuning parameters of Crow Search Algorithm are reduced by replacing the static flight length parameter with our dynamic flight length distribution algorithm. Third, the target selection method (random selection) is replaced by tournament select method. The proposed framework is used to search for architectures on MNIST, CIFAR10, and CIFAR100 datasets and achieved 0.18%, 3.48%, and 15.64% test error, respectively. Furthermore, small-scale transfer experiments are conducted to search architectures for Tiny ImageNet and achieved 34.43% test error. Nonparametric statistical analysis is performed to validate the impact of each modification in improving the quality of search space exploration. The proposed framework has achieved comparable performance with the state-of-the-art approaches, with a comparatively simpler approach and minimum human intervention. The proposed framework can be used to develop completely automated systems for designing architectures for various data-based classification applications.

## 16520. Mask-guided noise restriction adversarial attacks for image classification

- 标题：Mask-guided noise restriction adversarial attacks for image classification
- 作者：Yexin Duan, Xingyu Zhou, Junhua Zou, Junyang Qiu, Jin Zhang, Zhisong Pan
- 年份：2020
- 出版日期：2020-11-13
- 类型：article
- 语言：en
- 来源：Computers & Security
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-4048
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.cose.2020.102111
- OpenAlex ID：https://openalex.org/W3098226106
- 落地页：https://doi.org/10.1016/j.cose.2020.102111
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Neural Network Applications, Anomaly Detection Techniques and Applications
- 关键词：Adversarial system, Computer science, Noise (video), Artificial intelligence, Salient, Binary number, Image (mathematics), Transferability, Rotation (mathematics), Deep neural networks, Perspective (graphical), Benchmarking, Binary classification, Pattern recognition (psychology), Computer vision, Deep learning, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16521. Visual Sentiment Analysis With Social Relations-Guided Multiattention Networks

- 标题：Visual Sentiment Analysis With Social Relations-Guided Multiattention Networks
- 作者：Jie Xu, Zhoujun Li, Feiran Huang, Chaozhuo Li, Philip S. Yu
- 年份：2020
- 出版日期：2020-11-11
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Cybernetics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2168-2267
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcyb.2020.3027766
- OpenAlex ID：https://openalex.org/W3099091124
- 落地页：https://doi.org/10.1109/tcyb.2020.3027766
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Visual Attention and Saliency Detection, Sentiment Analysis and Opinion Mining
- 关键词：Computer science, Discriminative model, Leverage (statistics), Artificial intelligence, Feature (linguistics), Sentiment analysis, Machine learning, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
These days, social media users tend to express their feelings through sharing images online. Capturing the emotions embedded in these social images involves great research challenges and practical values. Most existing works concentrate on extracting the visual feature from a global view, while ignoring the fact that visual objects are also rich in emotion. How to leverage the multilevel visual features to improve the sentiment analysis performance is important yet challenging. Besides, existing works view each social image as an independent sample while ignoring the rich correlations among social images, which may be helpful in detecting visual emotion. In this article, we propose a novel model called social relations-guided multiattention networks (SRGMANs) to incorporate both the multilevel (region-level and object-level) visual features of a single image and the correlations among multiple social images to conduct visual sentiment analysis. Specifically, we first construct a heterogeneous network consisting of various types of social relations and introduce a heterogeneous network embedding method to learn the network representation for each image. Then, two visual attention branches (region attention network and object attention network) are devised to extract emotional and discriminative visual features. For each branch, we design a self-attention module to capture the emotional dependencies among visual parts. Besides, a network-guided attention module is also designed in each branch to focus on more network-related emotional visual parts with the guidance of the topology information. Finally, the attended visual features from the two attention models, together with network representation features, are combined within a holistic framework to predict the sentiment of social images. Extensive experiments demonstrate the superiority of our model on three benchmark datasets.

## 16522. An IRL-based malware adversarial generation method to evade anti-malware engines

- 标题：An IRL-based malware adversarial generation method to evade anti-malware engines
- 作者：Xintong Li, Qi Li
- 年份：2020
- 出版日期：2020-11-18
- 类型：article
- 语言：en
- 来源：Computers & Security
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-4048
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.cose.2020.102118
- OpenAlex ID：https://openalex.org/W3102543338
- 落地页：https://doi.org/10.1016/j.cose.2020.102118
- 主主题：Advanced Malware Detection Techniques
- 主题：Advanced Malware Detection Techniques, Adversarial Robustness in Machine Learning, Network Security and Intrusion Detection
- 关键词：Malware, Computer science, Adversarial system, Executable, Cryptovirology, Flexibility (engineering), Reinforcement learning, Adversarial machine learning, Artificial intelligence, Machine learning, Code (set theory), Set (abstract data type), Variety (cybernetics), Computer security, Data mining, Operating system, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16523. Adaptively Clustering-Driven Learning for Visual Relationship Detection

- 标题：Adaptively Clustering-Driven Learning for Visual Relationship Detection
- 作者：An-An Liu, Yanhui Wang, Ning Xu, Weizhi Nie, Jie Nie, Yongdong Zhang
- 年份：2020
- 出版日期：2020-12-10
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2020.3043084
- OpenAlex ID：https://openalex.org/W3111980808
- 落地页：https://doi.org/10.1109/tmm.2020.3043084
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Human Pose and Action Recognition
- 关键词：Cluster analysis, Computer science, Inference, Leverage (statistics), Artificial intelligence, Linear subspace, Discriminative model, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Visual relationship detection aims to describe the interactions between pairs of objects, such as <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">person-ride-bike</i> and <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">bike-next to-car</i> triplets. In reality, it is often the case that there exist some groups of strongly correlated relationships, while others are weakly related. Intuitively, the common relationships can be roughly categorized into several types such as geometric (e.g., next to), action (e.g., ride), and so on. However, previous studies ignore the relatedness discovery among multiple relationships, which only lie on a unified space to leverage visual features or statistical dependencies into categories. To tackle this problem, we propose an adaptively clustering-driven network for visual relationship detection, which can implicitly divide the unified relationship space into several subspaces with specific characteristics. Particularly, we propose two novel modules to discover the common distribution space and latent relationship association, respectively, which map pairs of object features into translation subspaces to induce the discriminative relationship clustering. Then, a fused inference is designed to integrate the group-induced representations with the language prior to facilitate the predicate inference. Especially, we design the Frobenius-norm regularization to boost the clustering. To the best of our knowledge, the proposed method is the first supervised framework to realize <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">subject-predicate-object</i> relationship-aware clustering for visual relationship detection. Extensive experiments show that the proposed method can achieve competing performances against the state-of-the-art methods on the Visual Genome dataset. Additional ablation studies further validate its effectiveness.

## 16524. Performing multi-target regression via gene expression programming-based ensemble models

- 标题：Performing multi-target regression via gene expression programming-based ensemble models
- 作者：Jose M. Moyano, Óscar Reyes, Habib M. Fardoun, Sebastián Ventura
- 年份：2020
- 出版日期：2020-12-28
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2020.12.060
- OpenAlex ID：https://openalex.org/W3114255665
- 落地页：https://doi.org/10.1016/j.neucom.2020.12.060
- 主主题：Evolutionary Algorithms and Applications
- 主题：Evolutionary Algorithms and Applications, Machine Learning and Data Classification, Viral Infectious Diseases and Gene Expression in Insects
- 关键词：Computer science, Genetic programming, Symbolic regression, Regression, Exploit, Population, Schema (genetic algorithms), Data mining, Gene expression programming, Regression analysis, Machine learning, Artificial intelligence, Set (abstract data type), Chromosome, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16525. Impact of Encoding of High Cardinality Categorical Data to Solve Prediction Problems

- 标题：Impact of Encoding of High Cardinality Categorical Data to Solve Prediction Problems
- 作者：Heena Gupta, V Asha
- 年份：2020
- 出版日期：2020-07-01
- 类型：article
- 语言：en
- 来源：Journal of Computational and Theoretical Nanoscience
- 来源类型：journal
- 出版方：American Scientific Publishers
- ISSN-L：1546-1955
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1166/jctn.2020.9044
- OpenAlex ID：https://openalex.org/W3114793362
- 落地页：https://doi.org/10.1166/jctn.2020.9044
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Data Mining Algorithms and Applications, Machine Learning and Data Classification
- 关键词：Cardinality (data modeling), Encoding (memory), Categorical variable, Domain (mathematical analysis), Computer science, Scheme (mathematics), Ordinal data, Data mining, Machine learning, Artificial intelligence, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The prediction problem in any domain is very important to assess the prices and preferences among people. This issue varies for different kinds of data. Data may be nominal or ordinal, it may involve more categories or less. For any category to be considered by a machine learning algorithm, it needs to be encoded before any other operation can be further performed. There are various encoding schemes available like label encoding, count encoding and one hot encoding. This paper aims to understand the impact of various encoding schemes and the accuracy among the prediction problems of high cardinality categorical data. The paper also proposes an encoding scheme based on curated strings. The domain chosen for this purpose is predicting doctors’ fees in various cities having different profiles and qualification.

## 16526. Adaptive Spatial Location With Balanced Loss for Video Captioning

- 标题：Adaptive Spatial Location With Balanced Loss for Video Captioning
- 作者：Linghui Li, Yongdong Zhang, Sheng Tang, Lingxi Xie, Xiaoyong Li, Qi Tian
- 年份：2020
- 出版日期：2020-12-18
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2020.3045735
- OpenAlex ID：https://openalex.org/W3115684750
- 落地页：https://doi.org/10.1109/tcsvt.2020.3045735
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Redundancy (engineering), Closed captioning, Artificial intelligence, Focus (optics), Sentence, Video tracking, Computer vision, Object (grammar), Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Many pioneering approaches have verified the effectiveness of utilizing the global temporal and local object information for video understanding tasks and have achieved significant progress. However, existing methods utilize object detectors to extract all objects overall video frames. This may bring performance degradation due to the information redundancy both spatially and temporally. To address this problem, we propose an adaptive spatial location module for the video captioning task which dynamically predicts an important position of each video frame in the procedure of generating the description sentence. The proposed adaptive spatial location method not only makes our model focus on local object information, but also reduces time and memory consumption brought by the temporal redundancy in extensive video frames and improves the accuracy of generated description. Besides, we propose a balanced loss function to address the class imbalance problem existing in training data. The proposed balanced loss assigns different weight to each word of ground-truth sentence in the training process which can generate more diversified description sentences. Extensive experimental results on the MSVD and MSR-VTT dataset show that the proposed method achieves competitive performance compared to state-of-the-art methods.

## 16527. Recent Progress in Automated Code Generation from GUI Images Using Machine Learning Techniques

- 标题：Recent Progress in Automated Code Generation from GUI Images Using Machine Learning Techniques
- 作者：Daniel Baulé, Christiane Gresse von Wangenheim, Aldo von Wangenheim, Jean Carlo Rossa Hauck
- 年份：2020
- 出版日期：2020-09-28
- 类型：article
- 语言：en
- 来源：JUCS - Journal of Universal Computer Science
- 来源类型：journal
- 出版方：Verlag der Technischen Universität Graz
- ISSN-L：0948-695X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.3897/jucs.2020.058
- OpenAlex ID：https://openalex.org/W3118136820
- 落地页：https://doi.org/10.3897/jucs.2020.058
- 开放 PDF 链接：https://lib.jucs.org/article/24108/download/pdf/
- 主主题：Software Engineering Research
- 主题：Software Engineering Research, Machine Learning and Data Classification, Software Engineering Techniques and Practices
- 关键词：Computer science, Automation, Process (computing), Code generation, Software engineering, Code (set theory), Graphical user interface, Machine learning, Human–computer interaction, Artificial intelligence, Programming language, Operating system, Key (lock), Set (abstract data type)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The manual transformation of a user interface design into code is a costly and time-consuming process. A solution can be the automation of the generation of code based on sketches or GUI design images. Recently, Machine Learning approaches have shown promising results in detecting GUI elements for such automation. Thus, to provide an overview of existing approaches, we performed a systematic mapping study. As a result, we identified and compared 20 approaches, that demonstrate good performance results being considered useful. These results can be used by researchers and practitioners in order to improve the efficiency of the GUI design process as well as continue to evolve and improve approaches for its support.

## 16528. 3-D Relation Network for visual relation recognition in videos

- 标题：3-D Relation Network for visual relation recognition in videos
- 作者：Qianwen Cao, Heyan Huang, Xindi Shang, Boran Wang, Tat‐Seng Chua
- 年份：2021
- 出版日期：2021-01-11
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2020.12.029
- OpenAlex ID：https://openalex.org/W3118923280
- 落地页：https://doi.org/10.1016/j.neucom.2020.12.029
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Advanced Image and Video Retrieval Techniques
- 关键词：Computer science, Relation (database), Artificial intelligence, Object (grammar), Task (project management), Feature (linguistics), Video tracking, Machine learning, Representation (politics), Spatial relation, Trajectory, Computer vision, Pattern recognition (psychology), Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16529. Pyramid regional graph representation learning for content-based video retrieval

- 标题：Pyramid regional graph representation learning for content-based video retrieval
- 作者：Guoping Zhao, Mingyu Zhang, Yaxian Li, Jiajun Liu, Bingqing Zhang, Ji-Rong Wen
- 年份：2021
- 出版日期：2021-01-13
- 类型：article
- 语言：en
- 来源：Information Processing & Management
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0306-4573
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ipm.2020.102488
- OpenAlex ID：https://openalex.org/W3119160203
- 落地页：https://doi.org/10.1016/j.ipm.2020.102488
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Video Analysis and Summarization, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Pyramid (geometry), Graph, Visual Word, Computer vision, Frame (networking), Image retrieval, Redundancy (engineering), Feature (linguistics), Pattern recognition (psychology), Information retrieval, Image (mathematics), Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16530. Cost-sensitive probability for weighted voting in an ensemble model for multi-class classification problems

- 标题：Cost-sensitive probability for weighted voting in an ensemble model for multi-class classification problems
- 作者：Artittayapron Rojarath, Wararat Songpan
- 年份：2021
- 出版日期：2021-01-06
- 类型：article
- 语言：en
- 来源：Applied Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0924-669X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s10489-020-02106-3
- OpenAlex ID：https://openalex.org/W3119162813
- 落地页：https://doi.org/10.1007/s10489-020-02106-3
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s10489-020-02106-3.pdf
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Machine Learning and Data Classification, Anomaly Detection Techniques and Applications
- 关键词：Computer science, Ensemble learning, Artificial intelligence, Machine learning, AdaBoost, Naive Bayes classifier, Random forest, Decision tree, Support vector machine, Ensemble forecasting, Classifier (UML), Perceptron, Voting, Weighted voting, Boosting (machine learning), Pattern recognition (psychology), Multilayer perceptron, Data mining, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Ensemble learning is an algorithm that utilizes various types of classification models. This algorithm can enhance the prediction efficiency of component models. However, the efficiency of combining models typically depends on the diversity and accuracy of the predicted results of ensemble models. However, the problem of multi-class data is still encountered. In the proposed approach, cost-sensitive learning was implemented to evaluate the prediction accuracy for each class, which was used to construct a cost-sensitivity matrix of the true positive (TP) rate. This TP rate can be used as a weight value and combined with a probability value to drive ensemble learning for a specified class. We proposed an ensemble model, which was a type of heterogenous model, namely, a combination of various individual classification models (support vector machine, Bayes, K-nearest neighbour, naïve Bayes, decision tree, and multi-layer perceptron) in experiments on 3-, 4-, 5- and 6-classifier models. The efficiencies of the propose models were compared to those of the individual classifier model and homogenous models (Adaboost, bagging, stacking, voting, random forest, and random subspaces) with various multi-class data sets. The experimental results demonstrate that the cost-sensitive probability for the weighted voting ensemble model that was derived from 3 models provided the most accurate results for the dataset in multi-class prediction. The objective of this study was to increase the efficiency of predicting classification results in multi-class classification tasks and to improve the classification results.

## 16531. PrivacyEye: A Privacy-Preserving and Computationally Efficient Deep Learning-Based Mobile Video Analytics System

- 标题：PrivacyEye: A Privacy-Preserving and Computationally Efficient Deep Learning-Based Mobile Video Analytics System
- 作者：Wei Du, Ang Li, Pan Zhou, Ben Niu, Dapeng Wu
- 年份：2021
- 出版日期：2021-01-13
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Mobile Computing
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：1536-1233
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmc.2021.3050458
- OpenAlex ID：https://openalex.org/W3120218917
- 落地页：https://doi.org/10.1109/tmc.2021.3050458
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Neural Network Applications, Privacy-Preserving Technologies in Data
- 关键词：Computer science, Cloud computing, Analytics, Mobile device, Convolutional neural network, Big data, Deep learning, Artificial intelligence, Feature extraction, Key (lock), Machine learning, Data mining, Computer security, World Wide Web
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Large volumes of video data recorded by the increasing mobile devices and embedded sensors can be leveraged to answer queries of our lives, physical world and our evolving society. Especially, the rapid development of convolutional neural networks (CNNs) in the past few years offers the great advantage for multiple tasks in video analysis. However, adopting running CNNs directly on mobile devices and embedded sensors for video analytics brings heavy burden due to their limited capacity, especially for learning a large volume of data. A promising approach is to outsource the computation-intensive part of CNN to cloud. However, the reveal of data to cloud may cause privacy leakage. In addition, the cloud-assisted approach may also bring some communication efficiency challenges for large volume of data. To address both privacy and efficiency issues, we design a privacy-preserving and computationally efficient framework for mobile video analytics. To protect the private information, we split the CNN model into two subnetworks, and first part is used as a feature extractor deployed in the mobile side and the second part is utilized as a classifier deployed in the cloud side. A specific-designed adversarial training process is adopted in order to extract features for normal task classification while hiding the features for sensitive task. In addition, to improve video process efficiency, we design a two-stage framework. The first stage is to extract key frames and necessary intermediate frames, while skipping redundant ones. The second stage is to extract the features of key frames by CNN-based feature extractor but apply optical-flow-based feature propagation algorithm to obtain the features of intermediate frames. Extensive experiments demonstrate our proposed system PrivacyEye can effectively protect private information while keep the accuracy of the normal tasks with less than 2 percent drop, and it saves up to 82.9 percent execution time and 78.8 percent energy consumption.

## 16532. SIMON: Open-Source Knowledge Discovery Platform

- 标题：SIMON: Open-Source Knowledge Discovery Platform
- 作者：Adriana Tomić, Ivan Tomic, Levi Waldron, Ludwig Geistlinger, Max Kühn, Rachel L. Spreng, Lindsay C. Dahora, Kelly E. Seaton, Georgia D. Tomaras, Jennifer Hill, Niharika A. Duggal, Ross D. Pollock
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：Patterns
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2666-3899
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1016/j.patter.2020.100178
- OpenAlex ID：https://openalex.org/W3121050787
- 落地页：https://doi.org/10.1016/j.patter.2020.100178
- 开放 PDF 链接：http://www.cell.com/article/S2666389920302427/pdf
- 主主题：Genetics, Bioinformatics, and Biomedical Research
- 主题：Genetics, Bioinformatics, and Biomedical Research, Gene expression and cancer classification, Machine Learning and Data Classification
- 关键词：Computer science, Data science, Modular design, Open source, Software, Resource (disambiguation), Interface (matter), Machine learning, Artificial intelligence, Software engineering, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Data analysis and knowledge discovery has become more and more important in biology and medicine with the increasing complexity of biological datasets, but the necessarily sophisticated programming skills and in-depth understanding of algorithms needed pose barriers to most biologists and clinicians to perform such research. We have developed a modular open-source software, SIMON, to facilitate the application of 180+ state-of-the-art machine-learning algorithms to high-dimensional biomedical data. With an easy-to-use graphical user interface, standardized pipelines, and automated approach for machine learning and other statistical analysis methods, SIMON helps to identify optimal algorithms and provides a resource that empowers non-technical and technical researchers to identify crucial patterns in biomedical data.

## 16533. Increasing the Confidence of Deep Neural Networks by Coverage Analysis

- 标题：Increasing the Confidence of Deep Neural Networks by Coverage Analysis
- 作者：Giulio Rossolini, Alessandro Biondi, Giorgio Buttazzo
- 年份：2022
- 出版日期：2022-03-30
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Software Engineering
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：0098-5589
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tse.2022.3163682
- OpenAlex ID：https://openalex.org/W3122715378
- 落地页：https://doi.org/10.1109/tse.2022.3163682
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Neural Network Applications, Anomaly Detection Techniques and Applications
- 关键词：Computer science, Adversarial system, Artificial intelligence, Deep learning, Robustness (evolution), Deep neural networks, Trustworthiness, Machine learning, Artificial neural network, Architecture, Robot, Adversarial machine learning, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The great performance of machine learning algorithms and deep neural networks in several perception and control tasks is pushing the industry to adopt such technologies in safety-critical applications, as autonomous robots and self-driving vehicles. At present, however, several issues need to be solved to make deep learning methods more trustworthy, predictable, safe, and secure against adversarial attacks. Although several methods have been proposed to improve the trustworthiness of deep neural networks, most of them are tailored for specific classes of adversarial examples, hence failing to detect other corner cases or unsafe inputs that heavily deviate from the training samples. This paper presents a lightweight monitoring architecture based on coverage paradigms to enhance the model robustness against different unsafe inputs. In particular, four coverage analysis methods are proposed and tested in the architecture for evaluating multiple detection logic. Experimental results show that the proposed approach is effective in detecting both powerful adversarial examples and out-of-distribution inputs, introducing limited extra-execution time and memory requirements.

## 16534. Deep supervised hashing using quadratic spherical mutual information for efficient image retrieval

- 标题：Deep supervised hashing using quadratic spherical mutual information for efficient image retrieval
- 作者：Nikolaos Passalis, Anastasios Tefas
- 年份：2021
- 出版日期：2021-01-18
- 类型：article
- 语言：en
- 来源：Signal Processing Image Communication
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0923-5965
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.image.2021.116146
- OpenAlex ID：https://openalex.org/W3123290832
- 落地页：https://doi.org/10.1016/j.image.2021.116146
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Video Surveillance and Tracking Methods, Multimodal Machine Learning Applications
- 关键词：Computer science, Mutual information, Hash function, Artificial intelligence, Measure (data warehouse), Quadratic equation, Image retrieval, Image (mathematics), Pattern recognition (psychology), Data mining, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16535. TextFirewall: Omni-Defending Against Adversarial Texts in Sentiment Classification

- 标题：TextFirewall: Omni-Defending Against Adversarial Texts in Sentiment Classification
- 作者：Wenqi Wang, Run Wang, Jianpeng Ke, Lina Wang
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2021.3058278
- OpenAlex ID：https://openalex.org/W3128993100
- 落地页：https://doi.org/10.1109/access.2021.3058278
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/9312710/09350600.pdf
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Hate Speech and Cyberbullying Detection
- 关键词：Adversarial system, Computer science, Natural language processing, Artificial intelligence, Sentiment analysis, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Sentiment classification has been broadly applied in real life, such as product recommendation and opinion-oriented analysis. Unfortunately, the widely employed sentiment classification systems based on deep neural networks (DNNs) are susceptible to adversarial attacks with imperceptible perturbations into the legitimate texts (also called <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">adversarial texts</i> ). Adversarial texts could cause erroneous outputs even without access to the target model, bringing security concerns to systems deployed in safety-critical applications. However, studies on defending against adversarial texts are still in the early stage and not ready for tackling the emerging threats, especially in dealing with unknown attacks. Investigating the minor differences between adversarial texts and legitimate texts and enhancing the robustness of target models are two mainstream ideas for defending against adversarial texts. However, both of them suffer the generalization issue in dealing with unknown adversarial attacks. In this paper, we proposed a general method, called <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">TextFirewall</i> , for defending against adversarial texts crafted by various adversarial attacks, which shows the potential in identifying new developed adversarial attacks in the future. Given a piece of text, our TextFirewall identifies the adversarial text by investigating the inconsistency between the target model’s output and the impact value calculated by important words in the text. TextFirewall could be deployed as a third-party tool without modifying the target model and agnostic to the specific type of adversarial texts. Experimental results demonstrate that our proposed TextFirewall effectively identifies adversarial texts generated by the three state-of-the-art (SOTA) attacks and outperforms previous defense techniques. Specifically, TextFirewall achieves an average accuracy of 90.7% on IMDB and 96.9% on Yelp in defending the three SOTA attacks.

## 16536. Prediction of Polycyclic Aromatic Hydrocarbons (PAHs) Removal from Wastewater Treatment Sludge Using Machine Learning Methods

- 标题：Prediction of Polycyclic Aromatic Hydrocarbons (PAHs) Removal from Wastewater Treatment Sludge Using Machine Learning Methods
- 作者：Burcu Çağlar Gençosman, Gizem EKER ŞANLI
- 年份：2021
- 出版日期：2021-02-18
- 类型：article
- 语言：en
- 来源：Water Air & Soil Pollution
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0049-6979
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11270-021-05049-8
- OpenAlex ID：https://openalex.org/W3129824677
- 落地页：https://doi.org/10.1007/s11270-021-05049-8
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Water Quality Monitoring Technologies, Water Quality Monitoring and Analysis
- 关键词：Random forest, Support vector machine, Artificial neural network, Decision tree, Computer science, Multilayer perceptron, Artificial intelligence, Wastewater, Machine learning, Perceptron, Environmental science, Environmental engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16537. Parallel-fusion LSTM with synchronous semantic and visual information for image captioning

- 标题：Parallel-fusion LSTM with synchronous semantic and visual information for image captioning
- 作者：Jing Zhang, Kangkang Li, Zhe Wang
- 年份：2021
- 出版日期：2021-02-01
- 类型：article
- 语言：en
- 来源：Journal of Visual Communication and Image Representation
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1047-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.jvcir.2021.103044
- OpenAlex ID：https://openalex.org/W3130531605
- 落地页：https://doi.org/10.1016/j.jvcir.2021.103044
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Closed captioning, Computer science, Artificial intelligence, Image (mathematics), Visualization, Natural language processing, Semantics (computer science), State (computer science), Speech recognition, Pattern recognition (psychology), Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16538. Application of Tensor Train Decomposition in S2VT Model for Sign Language Recognition

- 标题：Application of Tensor Train Decomposition in S2VT Model for Sign Language Recognition
- 作者：Biao Xu, Shiliang Huang, Zhongfu Ye
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2021.3059660
- OpenAlex ID：https://openalex.org/W3131590103
- 落地页：https://doi.org/10.1109/access.2021.3059660
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/9312710/09354800.pdf
- 主主题：Hand Gesture Recognition Systems
- 主题：Hand Gesture Recognition Systems, Human Pose and Action Recognition, Multimodal Machine Learning Applications
- 关键词：Computer science, Tensor (intrinsic definition), Sign language, Language model, Bridging (networking), Sequence (biology), Sign (mathematics), Speech recognition, Artificial intelligence, Word (group theory), Natural language processing, Mathematics, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Sign language recognition is a conversion of sign language into text or speech, bridging the communication between the hearing and society. Recently, sequence-to-sequence video to text (S2VT) models has been employed in the field of sign language recognition as an effective method. However, more than 20 million parameters trained in S2VT models will result in a huge consumption in memory and computational resources, making it hard to be applied in mobile devices. In order to overcome this issue, we proposed to employ tensor-train decomposition in S2VT models to reduce the parameters. First, the impact of parameters of tensor-train factorization on the model performance was investigated systematically. After that, we applied tensor-train decomposition in different layers of a S2VT model to establish 6 tensor-train S2VT models for Chinese sign language recognition. The experimental results demonstrated that when the fully-connected layer and the first LSTM layer in S2VT was represented with tensor-train format, the model could obtain the best performance, remaining high accuracy and reducing parameters and memory significantly. The proposed tensor-train S2VT models can also be applied in other sequence-to-sequence problems to improve the performance.

## 16539. Regular Polytope Networks

- 标题：Regular Polytope Networks
- 作者：Federico Pernici, Matteo Bruni, Claudio Baecchi, Alberto Del Bimbo
- 年份：2021
- 出版日期：2021-02-20
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks and Learning Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-237X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tnnls.2021.3056762
- OpenAlex ID：https://openalex.org/W3132598136
- 落地页：https://doi.org/10.1109/tnnls.2021.3056762
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Machine Learning and Algorithms, Neural Networks and Applications
- 关键词：Polytope, Simplex, Classifier (UML), Embedding, Computer science, Artificial neural network, Artificial intelligence, Mathematics, Combinatorics, Algorithm, Theoretical computer science, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Neural networks are widely used as a model for classification in a large variety of tasks. Typically, a learnable transformation (i.e., the classifier) is placed at the end of such models returning a value for each class used for classification. This transformation plays an important role in determining how the generated features change during the learning process. In this work, we argue that this transformation not only can be fixed (i.e., set as nontrainable) with no loss of accuracy and with a reduction in memory usage, but it can also be used to learn stationary and maximally separated embeddings. We show that the stationarity of the embedding and its maximal separated representation can be theoretically justified by setting the weights of the fixed classifier to values taken from the coordinate vertices of the three regular polytopes available in [Formula: see text], namely, the d -Simplex, the d -Cube, and the d -Orthoplex. These regular polytopes have the maximal amount of symmetry that can be exploited to generate stationary features angularly centered around their corresponding fixed weights. Our approach improves and broadens the concept of a fixed classifier, recently proposed by Hoffer et al., to a larger class of fixed classifier models. Experimental results confirm the theoretical analysis, the generalization capability, the faster convergence, and the improved performance of the proposed method. Code will be publicly available.

## 16540. Learning from group supervision: the impact of supervision deficiency on multi-label learning

- 标题：Learning from group supervision: the impact of supervision deficiency on multi-label learning
- 作者：Miao Xu, Lan-Zhe Guo
- 年份：2021
- 出版日期：2021-02-07
- 类型：article
- 语言：en
- 来源：Science China Information Sciences
- 来源类型：journal
- 出版方：Springer Nature
- ISSN-L：1674-733X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11432-020-3132-4
- OpenAlex ID：https://openalex.org/W3132705271
- 落地页：https://doi.org/10.1007/s11432-020-3132-4
- 主主题：Text and Document Classification Technologies
- 主题：Text and Document Classification Technologies, Machine Learning and Algorithms, Spam and Phishing Detection
- 关键词：Crowdsourcing, Computer science, Machine learning, Artificial intelligence, Annotation, Labeled data, Supervised learning, Artificial neural network, Semi-supervised learning, World Wide Web
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16541. MRCC: A Practical Covert Channel Over Monero With Provable Security

- 标题：MRCC: A Practical Covert Channel Over Monero With Provable Security
- 作者：Zhaozhong Guo, Liucheng Shi, Maozhi Xu, Yin Hong
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2021.3060285
- OpenAlex ID：https://openalex.org/W3133431973
- 落地页：https://doi.org/10.1109/access.2021.3060285
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/9312710/09356584.pdf
- 主主题：Internet Traffic Analysis and Secure E-voting
- 主题：Internet Traffic Analysis and Secure E-voting, Adversarial Robustness in Machine Learning, Advanced Steganography and Watermarking Techniques
- 关键词：Covert channel, Computer science, Communication source, Covert, Computer security, Anonymity, Channel (broadcasting), Key (lock), Protocol (science), Information hiding, Adversary, Public-key cryptography, Computer network, Encryption, Artificial intelligence, Cloud computing security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Covert channels are designed to protect the communication relationship of the sender and receiver. Traditional covert channels have become insecure due to the continuous improvement of traffic analysis techniques. In this context, there is an urgent need to identify new approaches for covert channels. Blockchain is an emerging technique with characteristics of user anonymity, a flooding propagation mechanism, and tamper resistance, which make it a compelling platform for covert channels. Previous approaches applied Bitcoin as the underlying blockchain, and its pseudoanonymity may expose the communication relationship. Moreover, the reliance of these approaches on prenegotiated labels to identify transactions containing covert messages further reduced their concealment. In this work, we present a practical and secure covert channel over Monero. Compared to Bitcoin, Monero's full anonymity efficiently protects the relationship between the sender and receiver. Moreover, no labels are employed to identify special transactions. The receiver filters and extracts the covert message using his private key. In this study, we make a complete assessment of the robustness, reliability, and anti-traceability of our protocol, as these properties are regarded as desirable for a covert channel. We also formalize the definition of security for covert channels through a transaction distinguishing experiment. A rigorous proof shows that our protocol meets this definition and is secure to use. Finally, we make a detailed comparison between our protocol and the existing blockchain-based covert channels.

## 16542. Robust hierarchical feature selection with a capped <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" altimg="si32.svg"><mml:mrow><mml:msub><mml:mrow><mml:mi>ℓ</mml:mi></mml:mrow><mml:mrow><mml:mn>2</mml:mn></mml:mrow></mml:msub></mml:mrow></mml:math>-norm

- 标题：Robust hierarchical feature selection with a capped <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" altimg="si32.svg"><mml:mrow><mml:msub><mml:mrow><mml:mi>ℓ</mml:mi></mml:mrow><mml:mrow><mml:mn>2</mml:mn></mml:mrow></mml:msub></mml:mrow></mml:math>-norm
- 作者：Xinxin Liu, Hong Zhao
- 年份：2021
- 出版日期：2021-03-10
- 类型：article
- 语言：lv
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2021.03.002
- OpenAlex ID：https://openalex.org/W3133826614
- 落地页：https://doi.org/10.1016/j.neucom.2021.03.002
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Imbalanced Data Classification Techniques, Machine Learning and Data Classification
- 关键词：Feature selection, Computer science, Artificial intelligence, Outlier, Discriminative model, Pattern recognition (psychology), Support vector machine, Robustness (evolution), Feature (linguistics), Dimensionality reduction, Machine learning, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16543. Dynamic feature selection algorithm based on Q-learning mechanism

- 标题：Dynamic feature selection algorithm based on Q-learning mechanism
- 作者：Ruohao Xu, Mengmeng Li, Zhongliang Yang, Lifang Yang, Kangjia Qiao, Zhigang Shang
- 年份：2021
- 出版日期：2021-03-01
- 类型：article
- 语言：en
- 来源：Applied Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0924-669X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10489-021-02257-x
- OpenAlex ID：https://openalex.org/W3134323307
- 落地页：https://doi.org/10.1007/s10489-021-02257-x
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Gene expression and cancer classification, Machine Learning and Data Classification
- 关键词：Computer science, Feature selection, Artificial intelligence, Benchmark (surveying), Feature (linguistics), Algorithm, Ranking (information retrieval), Pattern recognition (psychology), Machine learning, Minimum redundancy feature selection, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16544. Modified forensic-based investigation algorithm for global optimization

- 标题：Modified forensic-based investigation algorithm for global optimization
- 作者：Yiğit Çağatay Kuyu, Fahri Vatansever
- 年份：2021
- 出版日期：2021-02-26
- 类型：article
- 语言：en
- 来源：Engineering With Computers
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0177-0667
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00366-021-01322-w
- OpenAlex ID：https://openalex.org/W3134721748
- 落地页：https://doi.org/10.1007/s00366-021-01322-w
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Advanced Multi-Objective Optimization Algorithms, Machine Learning and Data Classification
- 关键词：Algorithm, Maxima and minima, Benchmark (surveying), Computer science, Metaheuristic, Jump, Mathematical optimization, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16545. A sentence-level text adversarial attack algorithm against IIoT based smart grid

- 标题：A sentence-level text adversarial attack algorithm against IIoT based smart grid
- 作者：Jialiang Dong, Zhitao Guan, Longfei Wu, Xiaojiang Du, Mohsen Guizani
- 年份：2021
- 出版日期：2021-03-07
- 类型：article
- 语言：en
- 来源：Computer Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1389-1286
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.comnet.2021.107956
- OpenAlex ID：https://openalex.org/W3135441826
- 落地页：https://doi.org/10.1016/j.comnet.2021.107956
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Smart Grid Security and Resilience, Advanced Malware Detection Techniques
- 关键词：Computer science, Adversarial system, Sentence, Computer security, Grid, Algorithm, Artificial intelligence, Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16546. The Implications of the No-Free-Lunch Theorems for Meta-induction

- 标题：The Implications of the No-Free-Lunch Theorems for Meta-induction
- 作者：David H. Wolpert
- 年份：2023
- 出版日期：2023-03-13
- 类型：article
- 语言：en
- 来源：Journal for General Philosophy of Science
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0044-2216
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10838-022-09609-2
- OpenAlex ID：https://openalex.org/W3136360370
- 落地页：https://doi.org/10.1007/s10838-022-09609-2
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Advanced Bandit Algorithms Research, Machine Learning and Data Classification
- 关键词：Mathematical induction, Inductive reasoning, Generalization, Backward induction, Inference, Set (abstract data type), Mathematics, Computer science, Algorithm, Discrete mathematics, Mathematical economics, Artificial intelligence, Game theory
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16547. Cybersecurity Issues in AI

- 标题：Cybersecurity Issues in AI
- 作者：Deepak Puthal, Saraju P. Mohanty
- 年份：2021
- 出版日期：2021-03-19
- 类型：article
- 语言：en
- 来源：IEEE Consumer Electronics Magazine
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-2248
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/mce.2021.3066828
- OpenAlex ID：https://openalex.org/W3137469725
- 落地页：https://doi.org/10.1109/mce.2021.3066828
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Privacy-Preserving Technologies in Data, Ethics and Social Impacts of AI
- 关键词：Computer security, Computer science, Process (computing), Information assurance, Information security, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
AI security is vital; however, it should be designed carefully by considering the suitable assurance processes based on system requirements. Data should be secure throughout the process of an AI system. The use case3 of self-driving cars is briefly considered.

## 16548. Robust graph convolutional networks with directional graph adversarial training

- 标题：Robust graph convolutional networks with directional graph adversarial training
- 作者：Weibo Hu, Chuan Chen, Yaomin Chang, Zibin Zheng, Yunfei Du
- 年份：2021
- 出版日期：2021-03-17
- 类型：article
- 语言：en
- 来源：Applied Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0924-669X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10489-021-02272-y
- OpenAlex ID：https://openalex.org/W3137885096
- 落地页：https://doi.org/10.1007/s10489-021-02272-y
- 主主题：Advanced Graph Neural Networks
- 主题：Advanced Graph Neural Networks, Adversarial Robustness in Machine Learning, Explainable Artificial Intelligence (XAI)
- 关键词：Computer science, Adversarial system, Graph, Robustness (evolution), Convolutional neural network, Theoretical computer science, Perturbation (astronomy), Artificial intelligence, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16549. Quality Inference in Federated Learning With Secure Aggregation

- 标题：Quality Inference in Federated Learning With Secure Aggregation
- 作者：Balázs Pejó, Gergely Biczók
- 年份：2023
- 出版日期：2023-05-29
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Big Data
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：2332-7790
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1109/tbdata.2023.3280406
- OpenAlex ID：https://openalex.org/W3138912819
- 落地页：https://doi.org/10.1109/tbdata.2023.3280406
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6687317/7153538/10138056.pdf
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Cryptography and Data Security, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Inference, Quality (philosophy), Confidentiality, Focus (optics), Information sensitivity, Data quality, Measure (data warehouse), Data mining, Artificial intelligence, Data science, Machine learning, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Federated learning algorithms are developed both for efficiency reasons and to ensure the privacy and confidentiality of personal and business data, respectively. Despite no data being shared explicitly, recent studies showed that the mechanism could still leak sensitive information. Hence, secure aggregation is utilized in many real-world scenarios to prevent attribution to specific participants. In this paper, we focus on the quality (i.e., the ratio of correct labels) of individual training datasets and show that such quality information could be inferred and attributed to specific participants even when secure aggregation is applied. Specifically, through a series of image recognition experiments, we infer the relative quality ordering of participants. Moreover, we apply the inferred quality information to stabilize training performance, measure the individual contribution of participants, and detect misbehavior.

## 16550. Bayesian neural architecture search using a training-free performance metric

- 标题：Bayesian neural architecture search using a training-free performance metric
- 作者：Andrés Camero, Hao Wang, Enrique Alba, Thomas Bäck
- 年份：2021
- 出版日期：2021-03-29
- 类型：article
- 语言：en
- 来源：Applied Soft Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1568-4946
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1016/j.asoc.2021.107356
- OpenAlex ID：https://openalex.org/W3139552059
- 落地页：https://doi.org/10.1016/j.asoc.2021.107356
- 开放 PDF 链接：https://www.sciencedirect.com/science/article/pii/S1568494621002799
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Neural Networks and Applications, Gaussian Processes and Bayesian Inference
- 关键词：Computer science, Hyperparameter, Bayesian optimization, Metric (unit), Categorical variable, Performance metric, Artificial intelligence, Encoding (memory), Representation (politics), Network architecture, Machine learning, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16551. Rotation Forest for Big Data

- 标题：Rotation Forest for Big Data
- 作者：Mario Juez-Gil, Álvar Arnaiz‐González, Juan J. Rodríguez, Carlos López Nozal, César García‐Osorio
- 年份：2021
- 出版日期：2021-03-27
- 类型：article
- 语言：en
- 来源：Information Fusion
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1566-2535
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.inffus.2021.03.007
- OpenAlex ID：https://openalex.org/W3145673679
- 落地页：https://doi.org/10.1016/j.inffus.2021.03.007
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Machine Learning and Data Classification, Anomaly Detection Techniques and Applications
- 关键词：Computer science, Random forest, Big data, Rotation (mathematics), Scalability, Naive Bayes classifier, Data mining, Classifier (UML), Artificial intelligence, Ensemble learning, SPARK (programming language), Pattern recognition (psychology), Machine learning, Database, Support vector machine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The Rotation Forest classifier is a successful ensemble method for a wide variety of data mining applications. However, the way in which Rotation Forest transforms the feature space through PCA, although powerful, penalizes training and prediction times, making it unfeasible for Big Data. In this paper, a MapReduce Rotation Forest and its implementation under the Spark framework are presented. The proposed MapReduce Rotation Forest behaves in the same way as the standard Rotation Forest, training the base classifiers on a rotated space, but using a functional implementation of the rotation that enables its execution in Big Data frameworks. Experimental results are obtained using different cloud-based cluster configurations. Bayesian tests are used to validate the method against two ensembles for Big Data: Random Forest and PCARDE classifiers. Our proposal incorporates the parallelization of both the PCA calculation and the tree training, providing a scalable solution that retains the performance of the original Rotation Forest and achieves a competitive execution time (in average, at training, more than 3 times faster than other PCA-based alternatives). In addition, extensive experimentation shows that by setting some parameters of the classifier (i.e., bootstrap sample size, number of trees, and number of rotations), the execution time is reduced with no significant loss of performance using a small ensemble.

## 16552. Entropy based C4.5-SHO algorithm with information gain optimization in data mining

- 标题：Entropy based C4.5-SHO algorithm with information gain optimization in data mining
- 作者：G. Sekhar Reddy, Suneetha Chittineni
- 年份：2021
- 出版日期：2021-04-07
- 类型：article
- 语言：en
- 来源：PeerJ Computer Science
- 来源类型：journal
- 出版方：PeerJ, Inc.
- ISSN-L：2376-5992
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.7717/peerj-cs.424
- OpenAlex ID：https://openalex.org/W3146518000
- 落地页：https://doi.org/10.7717/peerj-cs.424
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Metaheuristic Optimization Algorithms Research, Data Stream Mining Techniques
- 关键词：Information gain ratio, Information gain, Computer science, Cuckoo search, Data mining, Ant colony optimization algorithms, Particle swarm optimization, Decision tree, Entropy (arrow of time), Mutual information, ID3, Algorithm, Artificial intelligence, Machine learning, Decision tree learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Information efficiency is gaining more importance in the development as well as application sectors of information technology. Data mining is a computer-assisted process of massive data investigation that extracts meaningful information from the datasets. The mined information is used in decision-making to understand the behavior of each attribute. Therefore, a new classification algorithm is introduced in this paper to improve information management. The classical C4.5 decision tree approach is combined with the Selfish Herd Optimization (SHO) algorithm to tune the gain of given datasets. The optimal weights for the information gain will be updated based on SHO. Further, the dataset is partitioned into two classes based on quadratic entropy calculation and information gain. Decision tree gain optimization is the main aim of our proposed C4.5-SHO method. The robustness of the proposed method is evaluated on various datasets and compared with classifiers, such as ID3 and CART. The accuracy and area under the receiver operating characteristic curve parameters are estimated and compared with existing algorithms like ant colony optimization, particle swarm optimization and cuckoo search.

## 16553. Together Recognizing, Localizing and Summarizing Actions in Egocentric Videos

- 标题：Together Recognizing, Localizing and Summarizing Actions in Egocentric Videos
- 作者：Abhimanyu Sahu, Ananda S. Chowdhury
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2021.3070732
- OpenAlex ID：https://openalex.org/W3146543470
- 落地页：https://doi.org/10.1109/tip.2021.3070732
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Multimodal Machine Learning Applications, Video Analysis and Summarization
- 关键词：Automatic summarization, Computer science, Artificial intelligence, Pattern recognition (psychology), Frame (networking), Computer vision, Graph, Feature extraction, Feature (linguistics), Action recognition, Construct (python library), Gaze
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Analysis of egocentric video has recently drawn attention of researchers in the computer vision as well as multimedia communities. In this paper, we propose a weakly supervised superpixel level joint framework for localization, recognition and summarization of actions in an egocentric video. We first recognize and localize single as well as multiple action(s) in each frame of an egocentric video and then construct a summary of these detected actions. The superpixel level solution helps in precise localization of actions in addition to improving the recognition accuracy. Superpixels are extracted within the central regions of the egocentric video frames; these central regions being determined through a previously developed center-surround model. A sparse spatio-temporal video representation graph is constructed in the deep feature space with the superpixels as nodes. A weakly supervised solution using random walks yields action labels for each superpixel. After determining action label(s) for each frame from its constituent superpixels, we apply a fractional knapsack type formulation for obtaining a summary (of actions). Experimental comparisons on publicly available ADL, GTEA, EGTEA Gaze+, EgoGesture, and EPIC-Kitchens datasets show the effectiveness of the proposed solution.

## 16554. Augmenting Few-Shot Learning With Supervised Contrastive Learning

- 标题：Augmenting Few-Shot Learning With Supervised Contrastive Learning
- 作者：Taemin Lee, Sungjoo Yoo
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2021.3074525
- OpenAlex ID：https://openalex.org/W3154613065
- 落地页：https://doi.org/10.1109/access.2021.3074525
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/9312710/09409075.pdf
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Machine Learning and ELM
- 关键词：Computer science, Artificial intelligence, Machine learning, Extractor, Pipeline (software), Feature (linguistics), Contrast (vision), Class (philosophy), Feature extraction, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Few-shot learning deals with a small amount of data which incurs insufficient performance with conventional cross-entropy loss. We propose a pretraining approach for few-shot learning scenarios. That is, considering that the feature extractor quality is a critical factor in few-shot learning, we augment the feature extractor using a contrastive learning technique. It is reported that supervised contrastive learning applied to base class training in transductive few-shot training pipeline leads to improved results, outperforming the state-of-the-art methods on Mini-ImageNet and CUB. Furthermore, our experiment shows that a much larger dataset is needed to retain few-shot classification accuracy when domain-shift degradation exists, and if our method is applied, the need for a large dataset is eliminated. The accuracy gain can be translated to a runtime reduction of <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$3.87\times $ </tex-math></inline-formula> in a resource-constrained environment.

## 16555. Reverse engineering imperceptible backdoor attacks on deep neural networks for detection and training set cleansing

- 标题：Reverse engineering imperceptible backdoor attacks on deep neural networks for detection and training set cleansing
- 作者：Zhen Xiang, David J. Miller, George Kesidis
- 年份：2021
- 出版日期：2021-04-22
- 类型：article
- 语言：en
- 来源：Computers & Security
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-4048
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.cose.2021.102280
- OpenAlex ID：https://openalex.org/W3157391214
- 落地页：https://doi.org/10.1016/j.cose.2021.102280
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Integrated Circuits and Semiconductor Failure Analysis, Anomaly Detection Techniques and Applications
- 关键词：Backdoor, Computer science, Classifier (UML), Artificial intelligence, Trojan, Training set, Pattern recognition (psychology), Class (philosophy), Set (abstract data type), Artificial neural network, Test set, Machine learning, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16556. Reinforcing learning in Deep Belief Networks through nature-inspired optimization

- 标题：Reinforcing learning in Deep Belief Networks through nature-inspired optimization
- 作者：Mateus Roder, Leandro A. Passos, Gustavo Henrique de Rosa, Victor Hugo C. de Albuquerque, João Paulo Papa
- 年份：2021
- 出版日期：2021-04-30
- 类型：article
- 语言：en
- 来源：Applied Soft Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1568-4946
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.asoc.2021.107466
- OpenAlex ID：https://openalex.org/W3157526696
- 落地页：https://doi.org/10.1016/j.asoc.2021.107466
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Adversarial Robustness in Machine Learning, Advanced Neural Network Applications
- 关键词：Reinforcement learning, Hyperparameter, Computer science, Deep belief network, Artificial intelligence, Regularization (linguistics), Residual, Metaheuristic, Deep learning, Machine learning, Optimization problem, Mathematical optimization, Algorithm, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16557. A new standard error based artificial bee colony algorithm and its applications in feature selection

- 标题：A new standard error based artificial bee colony algorithm and its applications in feature selection
- 作者：Kazım Hanbay
- 年份：2021
- 出版日期：2021-05-04
- 类型：article
- 语言：en
- 来源：Journal of King Saud University - Computer and Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1319-1578
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.jksuci.2021.04.010
- OpenAlex ID：https://openalex.org/W3157657823
- 落地页：https://doi.org/10.1016/j.jksuci.2021.04.010
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Face and Expression Recognition, Machine Learning and Data Classification
- 关键词：Artificial bee colony algorithm, Feature selection, Computer science, Particle swarm optimization, Artificial intelligence, k-nearest neighbors algorithm, Support vector machine, Pattern recognition (psychology), Algorithm, Entropy (arrow of time), Feature vector, Feature (linguistics), Selection (genetic algorithm), Genetic algorithm, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Feature selection is a basic task for pattern recognition and classification. It enhances the performance of the classification algorithms with the help of removing the redundant features. Thanks to eliminating irrelevant features, the computational time is decreased. Thus, intensive works have been carried out in this area. This paper proposes a new standard error-based artificial bee colony (SEABC) algorithm for the feature selection problem, which is developed by integrating standard error-based new solution search mechanisms into the original artificial bee colony algorithm. The SEABC algorithm is used for feature selection. Shannon entropy function is used to serve as the objective function of the SEABC algorithm. Thirteen datasets are used from UCI machine learning datasets. Features are selected according to Shannon conditional entropy values and then a threshold process is implemented to find their best relevant subset. Support Vector Machines (SVMs) and k-Nearest Neighbor (KNN) are used as the optimal classifiers. The proposed SEABC algorithm is compared with genetic algorithm (GA), particle swarm optimization (PSO), ABC, improved ABC (I-ABC), Gbest-guided ABC (GABC), and PS-ABC algorithms. In general, it is observed that the SEABC algorithm achieves better classification results than other well-known algorithms.

## 16558. Modality adaptation in multimodal data

- 标题：Modality adaptation in multimodal data
- 作者：Parvin Razzaghi, Karim Abbasi, Mahmoud Shirazi, Niloofar Shabani
- 年份：2021
- 出版日期：2021-04-28
- 类型：article
- 语言：en
- 来源：Expert Systems with Applications
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0957-4174
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.eswa.2021.115126
- OpenAlex ID：https://openalex.org/W3157841754
- 落地页：https://doi.org/10.1016/j.eswa.2021.115126
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Advanced Neural Network Applications
- 关键词：Modality (human–computer interaction), Computer science, Modalities, Adaptation (eye), Artificial intelligence, Multimodal learning, Machine learning, Discriminative model, Domain adaptation
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16559. Centerness-Aware Network for Temporal Action Proposal

- 标题：Centerness-Aware Network for Temporal Action Proposal
- 作者：Liu Yuan, Jingyuan Chen, Xinpeng Chen, Bing Deng, Jianqiang Huang, Xian‐Sheng Hua
- 年份：2021
- 出版日期：2021-04-26
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2021.3075607
- OpenAlex ID：https://openalex.org/W3158201658
- 落地页：https://doi.org/10.1109/tcsvt.2021.3075607
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Multimodal Machine Learning Applications, Video Analysis and Summarization
- 关键词：Computer science, Boundary (topology), Action (physics), Point (geometry), Artificial intelligence, Feature (linguistics), Key (lock), Action recognition, Ground truth, State (computer science), Adaptation (eye), Pattern recognition (psychology), Movement (music), Computer vision, Algorithm, Mathematics, Class (philosophy)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Temporal action proposal generation aims at localizing the temporal segments containing human actions in a video. This work proposes a centerness-aware network (CAN), which is a novel one-stage approach intended to generate action proposals as keypoint triplets. A keypoint triplet contains two boundary points (starting and ending) and one center point. Specifically, we evaluate the probabilities of each temporal location in the video whether it is at the boundaries or the center region of ground truth action proposals. CAN optimizes the predicted boundary points interactively in a bidirectional adaptation form by exploiting the dependencies among them. Furthermore, to accurately locate the center points of action proposals with different time spans, temporal feature pyramids are utilized to incorporate multi-scale information explicitly. Using the generated three keypoints, CAN efficiently retrieves temporal proposals by grouping keypoints into triplets if they are geometrically aligned. Experiments show that CAN achieves the state-of-the-art performance on the public THUMOS-14 and ActivityNet-1.3 datasets. Moreover, further experiments demonstrate that by applying action classifiers on proposals generated by CAN, our method achieves the state-of-the-art performance in temporal action localization.

## 16560. Graph-Based Visual-Semantic Entanglement Network for Zero-Shot Image Recognition

- 标题：Graph-Based Visual-Semantic Entanglement Network for Zero-Shot Image Recognition
- 作者：Yang Hu, Guihua Wen, Adriane Chapman, Pei Yang, Mingnan Luo, Yingxue Xu, Dan Dai, Wendy Hall
- 年份：2021
- 出版日期：2021-05-20
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tmm.2021.3082292
- OpenAlex ID：https://openalex.org/W3164027444
- 落地页：https://doi.org/10.1109/tmm.2021.3082292
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Advanced Neural Network Applications
- 关键词：Computer science, Artificial intelligence, Convolutional neural network, Graph, Pattern recognition (psychology), Ambiguity, Visualization, Semantic similarity, Theoretical computer science, Natural language processing
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Zero-shot learning uses semantic attributes to connect the search space of unseen objects. In recent years, although the deep convolutional network brings powerful visual modeling capabilities to the ZSL task, its visual features have severe pattern inertia and lack of representation of semantic relationships, which leads to severe bias and ambiguity. In response to this, we propose the Graph-based Visual-Semantic Entanglement Network to conduct graph modeling of visual features, which is mapped to semantic attributes by using a knowledge graph, it contains several novel designs: 1. it establishes a multi-path entangled network with the convolutional neural network (CNN) and the graph convolutional network (GCN), which input the visual features from CNN to GCN to model the implicit semantic relations, then GCN feedback the graph modeled information to CNN features; 2. it uses attribute word vectors as the target for the graph semantic modeling of GCN, which forms a self-consistent regression for graph modeling and supervise GCN to learn more personalized attribute relations; 3. it fuses and supplements the hierarchical visual-semantic features refined by graph modeling into visual embedding. Our method outperforms state-of-the-art approaches on multiple representative ZSL datasets: AwA2, CUB, and SUN by promoting the semantic linkage modelling of visual features.

## 16561. Ethical Adversaries

- 标题：Ethical Adversaries
- 作者：Pieter Delobelle, Paul Temple, Gilles Perrouin, Benoît Frénay‬, Patrick Heymans, Bettina Berendt
- 年份：2021
- 出版日期：2021-05-26
- 类型：article
- 语言：en
- 来源：ACM SIGKDD Explorations Newsletter
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1931-0145
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/3468507.3468513
- OpenAlex ID：https://openalex.org/W3165435112
- 落地页：https://doi.org/10.1145/3468507.3468513
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Ethics and Social Impacts of AI, Explainable Artificial Intelligence (XAI)
- 关键词：Computer science, Notice, Scrutiny, Adversarial system, Limiting, Evasion (ethics), Hyperparameter, Machine learning, Risk analysis (engineering), Artificial intelligence, Law
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Machine learning is being integrated into a growing number of critical systems with far-reaching impacts on society. Unexpected behaviour and unfair decision processes are coming under increasing scrutiny due to this widespread use and its theoretical considerations. Individuals, as well as organisations, notice, test, and criticize unfair results to hold model designers and deployers accountable. We offer a framework that assists these groups in mitigating unfair representations stemming from the training datasets. Our framework relies on two inter-operating adversaries to improve fairness. First, a model is trained with the goal of preventing the guessing of protected attributes' values while limiting utility losses. This first step optimizes the model's parameters for fairness. Second, the framework leverages evasion attacks from adversarial machine learning to generate new examples that will be misclassified. These new examples are then used to retrain and improve the model in the first step. These two steps are iteratively applied until a significant improvement in fairness is obtained. We evaluated our framework on well-studied datasets in the fairness literature - including COMPAS - where it can surpass other approaches concerning demographic parity, equality of opportunity and also the model's utility. We investigated the trade-offs between these targets in terms of model hyperparameters and also illustrated our findings on the subtle difficulties when mitigating unfairness and highlight how our framework can assist model designers.

## 16562. Analysis of convolutional neural network image classifiers in a hierarchical max-pooling model with additional local pooling

- 标题：Analysis of convolutional neural network image classifiers in a hierarchical max-pooling model with additional local pooling
- 作者：Benjamin Walter
- 年份：2022
- 出版日期：2022-11-08
- 类型：article
- 语言：en
- 来源：Journal of Statistical Planning and Inference
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0378-3758
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.jspi.2022.11.001
- OpenAlex ID：https://openalex.org/W3170432162
- 落地页：https://doi.org/10.1016/j.jspi.2022.11.001
- 主主题：Image and Signal Denoising Methods
- 主题：Image and Signal Denoising Methods, Neural Networks and Applications, Machine Learning and Data Classification
- 关键词：Pooling, Convolutional neural network, Artificial intelligence, Computer science, Pattern recognition (psychology), Contextual image classification, Image (mathematics), Artificial neural network, Sample (material), Machine learning, Data mining, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16563. NetFense: Adversarial Defenses against Privacy Attacks on Neural Networks for Graph Data

- 标题：NetFense: Adversarial Defenses against Privacy Attacks on Neural Networks for Graph Data
- 作者：I-Chung Hsieh, Cheng–Te Li
- 年份：2021
- 出版日期：2021-06-09
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Knowledge and Data Engineering
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：1041-4347
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1109/tkde.2021.3087515
- OpenAlex ID：https://openalex.org/W3171131018
- 落地页：https://doi.org/10.1109/tkde.2021.3087515
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/69/9973432/09448513.pdf
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Advanced Graph Neural Networks, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Adversarial system, Adversary, Social graph, Graph, Information privacy, Theoretical computer science, Data mining, Differential privacy, Computer security, Machine learning, Artificial intelligence, Social media
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Recent advances in protecting node privacy on graph data and attacking graph neural networks (GNNs) gain much attention. The eye does not bring these two essential tasks together yet. Imagine an adversary can utilize the powerful GNNs to infer users’ private labels in a social network. How can we adversarially defend against such privacy attacks while maintaining the utility of perturbed graphs? In this work, we propose a novel research task, adversarial defenses against GNN-based privacy attacks, and present a graph perturbation-based approach, NetFense, to achieve the goal. NetFense can simultaneously keep graph data unnoticeability (i.e., having limited changes on the graph structure), maintain the prediction confidence of targeted label classification (i.e., preserving data utility), and reduce the prediction confidence of private label classification (i.e., protecting the privacy of nodes). Experiments conducted on single- and multiple-target perturbations using three real graph data exhibit that the perturbed graphs by NetFense can effectively maintain data utility (i.e., model unnoticeability) on targeted label classification and significantly decrease the prediction confidence of private label classification (i.e., privacy protection). Extensive studies also bring several insights, such as the flexibility of NetFense, preserving local neighborhoods in data unnoticeability, and better privacy protection for high-degree nodes.

## 16564. Explainable artificial intelligence in forensics: Realistic explanations for number of contributor predictions of DNA profiles

- 标题：Explainable artificial intelligence in forensics: Realistic explanations for number of contributor predictions of DNA profiles
- 作者：Marthe S. Veldhuis, Simone Ariëns, Rolf J.F. Ypma, Thomas Abeel, Corina C.G. Benschop
- 年份：2021
- 出版日期：2021-11-21
- 类型：article
- 语言：en
- 来源：Forensic Science International Genetics
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1872-4973
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.fsigen.2021.102632
- OpenAlex ID：https://openalex.org/W3171159528
- 落地页：https://doi.org/10.1016/j.fsigen.2021.102632
- 主主题：Explainable Artificial Intelligence (XAI)
- 主题：Explainable Artificial Intelligence (XAI), Adversarial Robustness in Machine Learning, Topic Modeling
- 关键词：Counterfactual thinking, Counterfactual conditional, Computer science, Leverage (statistics), Machine learning, Metric (unit), Artificial intelligence, Visualization, Focus (optics), Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16565. Dynamic Instance-wise Joint Feature Selection and Classification

- 标题：Dynamic Instance-wise Joint Feature Selection and Classification
- 作者：Yasitha Warahena Liyanage, Daphney–Stavroula Zois, Charalampos Chelmis
- 年份：2021
- 出版日期：2021-04-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Artificial Intelligence
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2691-4581
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tai.2021.3077212
- OpenAlex ID：https://openalex.org/W3174998861
- 落地页：https://doi.org/10.1109/tai.2021.3077212
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Face and Expression Recognition, Anomaly Detection Techniques and Applications
- 关键词：Computer science, Scalability, Data mining, Feature selection, Machine learning, Set (abstract data type), Artificial intelligence, Process (computing), Feature (linguistics), Selection (genetic algorithm)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this article, a dynamic instance-wise joint feature selection and classification framework during testing is presented. Specifically, the proposed framework sequentially selects features one at a time for each data instance, given previously selected features, and stops this process to classify the instance once it determines that including additional features will not improve the final classification decision. In contrast to most of the existing work that utilizes a set of features, common for all data instances, the proposed framework utilizes different features to classify each data instance. An optimization problem is defined for each data instance in terms of the number of selected features and the associated classification accuracy. The optimum solution is derived, and its structure is analyzed. Based on the optimum solution and its properties, two new algorithms are designed. The expected number of features needed to achieve a given classification accuracy is also analytically derived. Finally, the performance of the proposed algorithms is illustrated on 11 public datasets, thus demonstrating their effectiveness and scalability across a broad range of application domains. Impact Statement-In many domains, including but not limited to medicine and criminal justice, experts need to reach an accurate decision in a timely manner using limited resources (e.g., costly tests and time-consuming evidence collection). At the same time, it is desirable to tailor decisions to each individual case (e.g., patient and defendant). Most of the existing machine learning algorithms, however, ignore resource constraints and/or acquire a general solution for all cases, while not scaling in big data settings. The algorithms proposed in this article address such challenges enabling tailored and timely decision making. With a reduction of up to 66% in the average number of features, while maintaining similar accuracy levels, the proposed algorithms can be used for dynamic instance-wise joint feature selection and classification in scenarios involving over one million variables.

## 16566. Novel Meta-Features for Automated Machine Learning Model Selection in Anomaly Detection

- 标题：Novel Meta-Features for Automated Machine Learning Model Selection in Anomaly Detection
- 作者：Miloš Kotlar, Marija Punt, Zaharije Radivojević, Miloš Cvetanović, Veljko Milutinović
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2021.3090936
- OpenAlex ID：https://openalex.org/W3175386426
- 落地页：https://doi.org/10.1109/access.2021.3090936
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/9312710/09461173.pdf
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Data Stream Mining Techniques, Anomaly Detection Techniques and Applications
- 关键词：Computer science, Meta learning (computer science), Anomaly detection, Machine learning, Artificial intelligence, Metric (unit), Set (abstract data type), Model selection, Feature selection, Data mining, Selection (genetic algorithm), Key (lock), Data set, Task (project management)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A growing number of research papers shed light on automated machine learning (AutoML) frameworks, which are becoming a promising solution for building complex machine learning models without human expertise and assistance. The key challenge in enabling AutoML frameworks to build an efficient model for anomaly detection tasks is to determine the best underlying model for a given task and optimization metric. The meta-learning approaches based on a set of meta-features that describes data properties can enable efficient model selection in AutoML frameworks. The existing meta-learning approaches based on statistical and information-theoretic meta-features require large amounts of data and computational resources to extract data properties. This paper proposes a novel set of meta-features for model selection in anomaly detection tasks based on domain-specific properties of data which overcomes the shortcomings of existing meta-features by introducing simple but effective meta-features that can be efficiently extracted or estimated by using a low amount of data. Experiments with 63 datasets from different repositories with varying schemas show that the proposed set of meta-features achieves an accuracy of 87% for model selection, while the achieved accuracy for simple meta-features is 74%, for statistical meta-features 68%, for information theory meta-feature 70%, and for a comprehensive set of meta-features by pyMFE 73%. This demonstrates that the proposed set can be adopted by AutoML frameworks across a diverse range of domains.

## 16567. Using Meta-Learning to predict student performance in virtual learning environments

- 标题：Using Meta-Learning to predict student performance in virtual learning environments
- 作者：Ángel Casado Hidalgo, Pablo Moreno‐Ger, Luis de‐la‐Fuente‐Valentín
- 年份：2021
- 出版日期：2021-07-06
- 类型：article
- 语言：en
- 来源：Applied Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0924-669X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10489-021-02613-x
- OpenAlex ID：https://openalex.org/W3179507752
- 落地页：https://doi.org/10.1007/s10489-021-02613-x
- 主主题：Online Learning and Analytics
- 主题：Online Learning and Analytics, Machine Learning and Data Classification, Data Stream Mining Techniques
- 关键词：Computer science, Scalability, Field (mathematics), Hyperparameter, Deep learning, Artificial intelligence, Data science, Big data, Machine learning, Educational data mining, Learning analytics, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16568. Using Machine Learning for Dependable Outlier Detection in Environmental Monitoring Systems

- 标题：Using Machine Learning for Dependable Outlier Detection in Environmental Monitoring Systems
- 作者：Gonçalo Jesus, António Casimiro, A. Oliveira
- 年份：2021
- 出版日期：2021-07-11
- 类型：article
- 语言：en
- 来源：ACM Transactions on Cyber-Physical Systems
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：2378-962X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/3445812
- OpenAlex ID：https://openalex.org/W3181721792
- 落地页：https://doi.org/10.1145/3445812
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Adversarial Robustness in Machine Learning, Water Systems and Optimization
- 关键词：Anomaly detection, Outlier, Computer science, Data mining, Data quality, Artificial intelligence, Machine learning, Real-time computing, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Sensor platforms used in environmental monitoring applications are often subject to harsh environmental conditions while monitoring complex phenomena. Therefore, designing dependable monitoring systems is challenging given the external disturbances affecting sensor measurements. Even the apparently simple task of outlier detection in sensor data becomes a hard problem, amplified by the difficulty in distinguishing true data errors due to sensor faults from deviations due to natural phenomenon, which look like data errors. Existing solutions for runtime outlier detection typically assume that the physical processes can be accurately modeled, or that outliers consist in large deviations that are easily detected and filtered by appropriate thresholds. Other solutions assume that it is possible to deploy multiple sensors providing redundant data to support voting-based techniques. In this article, we propose a new methodology for dependable runtime detection of outliers in environmental monitoring systems, aiming to increase data quality by treating them. We propose the use of machine learning techniques to model each sensor behavior, exploiting the existence of correlated data provided by other related sensors. Using these models, along with knowledge of processed past measurements, it is possible to obtain accurate estimations of the observed environment parameters and build failure detectors that use these estimations. When a failure is detected, these estimations also allow one to correct the erroneous measurements and hence improve the overall data quality. Our methodology not only allows one to distinguish truly abnormal measurements from deviations due to complex natural phenomena, but also allows the quantification of each measurement quality, which is relevant from a dependability perspective. We apply the methodology to real datasets from a complex aquatic monitoring system, measuring temperature and salinity parameters, through which we illustrate the process for building the machine learning prediction models using a technique based on Artificial Neural Networks, denoted ANNODE ( ANN Outlier Detection ). From this application, we also observe the effectiveness of our ANNODE approach for accurate outlier detection in harsh environments. Then we validate these positive results by comparing ANNODE with state-of-the-art solutions for outlier detection. The results show that ANNODE improves existing solutions regarding accuracy of outlier detection.

## 16569. Proximal Policy Optimization for Radiation Source Search

- 标题：Proximal Policy Optimization for Radiation Source Search
- 作者：Philippe Proctor, Christof Teuscher, Adam Hecht, Marek Osiński
- 年份：2021
- 出版日期：2021-09-30
- 类型：article
- 语言：en
- 来源：Journal of Nuclear Engineering
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2673-4362
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/jne2040029
- OpenAlex ID：https://openalex.org/W3188537898
- 落地页：https://doi.org/10.3390/jne2040029
- 开放 PDF 链接：https://www.mdpi.com/2673-4362/2/4/29/pdf?version=1634786863
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Nuclear reactor physics and engineering, Distributed Sensor Networks and Detection Algorithms
- 关键词：Reinforcement learning, Computer science, Context (archaeology), Detector, Controller (irrigation), Convex optimization, Filter (signal processing), Algorithm, Real-time computing, Physics, Mathematical optimization, Regular polygon, Mathematics, Artificial intelligence, Computer vision
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Rapid search and localization for nuclear sources can be an important aspect in preventing human harm from illicit material in dirty bombs or from contamination. In the case of a single mobile radiation detector, there are numerous challenges to overcome such as weak source intensity, multiple sources, background radiation, and the presence of obstructions, i.e., a non-convex environment. In this work, we investigate the sequential decision making capability of deep reinforcement learning in the nuclear source search context. A novel neural network architecture (RAD-A2C) based on the advantage actor critic (A2C) framework and a particle filter gated recurrent unit for localization is proposed. Performance is studied in a randomized 20×20 m convex and non-convex simulation environment across a range of signal-to-noise ratio (SNR)s for a single detector and single source. RAD-A2C performance is compared to both an information-driven controller that uses a bootstrap particle filter and to a gradient search (GS) algorithm. We find that the RAD-A2C has comparable performance to the information-driven controller across SNR in a convex environment. The RAD-A2C far outperforms the GS algorithm in the non-convex environment with greater than 95% median completion rate for up to seven obstructions.

## 16570. Toward Learning Trustworthily from Data Combining Privacy, Fairness, and Explainability: An Application to Face Recognition

- 标题：Toward Learning Trustworthily from Data Combining Privacy, Fairness, and Explainability: An Application to Face Recognition
- 作者：Danilo Franco, Luca Oneto, Nicolò Navarin, Davide Anguita
- 年份：2021
- 出版日期：2021-08-14
- 类型：article
- 语言：en
- 来源：Entropy
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1099-4300
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/e23081047
- OpenAlex ID：https://openalex.org/W3193910443
- 落地页：https://doi.org/10.3390/e23081047
- 开放 PDF 链接：https://www.mdpi.com/1099-4300/23/8/1047/pdf?version=1629206735
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Adversarial Robustness in Machine Learning, Ethics and Social Impacts of AI
- 关键词：Computer science, Homomorphic encryption, Facial recognition system, Face (sociological concept), Artificial intelligence, Internet privacy, Representation (politics), Encryption, Machine learning, Data science, Computer security, Politics, Pattern recognition (psychology), Political science, Sociology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In many decision-making scenarios, ranging from recreational activities to healthcare and policing, the use of artificial intelligence coupled with the ability to learn from historical data is becoming ubiquitous. This widespread adoption of automated systems is accompanied by the increasing concerns regarding their ethical implications. Fundamental rights, such as the ones that require the preservation of privacy, do not discriminate based on sensible attributes (e.g., gender, ethnicity, political/sexual orientation), or require one to provide an explanation for a decision, are daily undermined by the use of increasingly complex and less understandable yet more accurate learning algorithms. For this purpose, in this work, we work toward the development of systems able to ensure trustworthiness by delivering privacy, fairness, and explainability by design. In particular, we show that it is possible to simultaneously learn from data while preserving the privacy of the individuals thanks to the use of Homomorphic Encryption, ensuring fairness by learning a fair representation from the data, and ensuring explainable decisions with local and global explanations without compromising the accuracy of the final models. We test our approach on a widespread but still controversial application, namely face recognition, using the recent FairFace dataset to prove the validity of our approach.

## 16571. Graph-Based Visual Manipulation Relationship Reasoning Network for Robotic Grasping

- 标题：Graph-Based Visual Manipulation Relationship Reasoning Network for Robotic Grasping
- 作者：Guoyu Zuo, Jiayuan Tong, Hongxing Liu, Wenbai Chen, Jianfeng Li
- 年份：2021
- 出版日期：2021-08-13
- 类型：article
- 语言：en
- 来源：Frontiers in Neurorobotics
- 来源类型：journal
- 出版方：Frontiers Media
- ISSN-L：1662-5218
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3389/fnbot.2021.719731
- OpenAlex ID：https://openalex.org/W3195127674
- 落地页：https://doi.org/10.3389/fnbot.2021.719731
- 开放 PDF 链接：https://www.frontiersin.org/articles/10.3389/fnbot.2021.719731/pdf
- 主主题：Robot Manipulation and Learning
- 主题：Robot Manipulation and Learning, Multimodal Machine Learning Applications, Soft Robotics and Applications
- 关键词：Computer science, GRASP, Artificial intelligence, Object (grammar), Robot, Graph, Scene graph, Computer vision, Generalization, Relation (database), Visual reasoning, Theoretical computer science, Data mining, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
To grasp the target object stably and orderly in the object-stacking scenes, it is important for the robot to reason the relationships between objects and obtain intelligent manipulation order for more advanced interaction between the robot and the environment. This paper proposes a novel graph-based visual manipulation relationship reasoning network (GVMRN) that directly outputs object relationships and manipulation order. The GVMRN model first extracts features and detects objects from RGB images, and then adopts graph convolutional network (GCN) to collect contextual information between objects. To improve the efficiency of relation reasoning, a relationship filtering network is built to reduce object pairs before reasoning. The experiments on the Visual Manipulation Relationship Dataset (VMRD) show that our model significantly outperforms previous methods on reasoning object relationships in object-stacking scenes. The GVMRN model is also tested on the images we collected and applied on the robot grasping platform. The results demonstrated the generalization and applicability of our method in real environment.

## 16572. Enabling Artificial Intelligence Adoption through Assurance

- 标题：Enabling Artificial Intelligence Adoption through Assurance
- 作者：Laura Freeman, Abdul Rahman, Feras A. Batarseh
- 年份：2021
- 出版日期：2021-08-25
- 类型：article
- 语言：en
- 来源：Social Sciences
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2076-0760
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/socsci10090322
- OpenAlex ID：https://openalex.org/W3195339943
- 落地页：https://doi.org/10.3390/socsci10090322
- 开放 PDF 链接：https://www.mdpi.com/2076-0760/10/9/322/pdf?version=1629864541
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Adversarial Robustness in Machine Learning, Data Stream Mining Techniques
- 关键词：Computer science, Quality assurance, Context (archaeology), Domain (mathematical analysis), Software security assurance, Safety assurance, Information assurance, Artificial intelligence, Software engineering, Computer security, Information security, Reliability engineering, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The wide scale adoption of Artificial Intelligence (AI) will require that AI engineers and developers can provide assurances to the user base that an algorithm will perform as intended and without failure. Assurance is the safety valve for reliable, dependable, explainable, and fair intelligent systems. AI assurance provides the necessary tools to enable AI adoption into applications, software, hardware, and complex systems. AI assurance involves quantifying capabilities and associating risks across deployments including: data quality to include inherent biases, algorithm performance, statistical errors, and algorithm trustworthiness and security. Data, algorithmic, and context/domain-specific factors may change over time and impact the ability of AI systems in delivering accurate outcomes. In this paper, we discuss the importance and different angles of AI assurance, and present a general framework that addresses its challenges.

## 16573. FSNet: A Failure Detection Framework for Semantic Segmentation

- 标题：FSNet: A Failure Detection Framework for Semantic Segmentation
- 作者：Quazi Marufur Rahman, Niko Sünderhauf, Peter Corke, Feras Dayoub
- 年份：2022
- 出版日期：2022-01-14
- 类型：article
- 语言：en
- 来源：IEEE Robotics and Automation Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2377-3766
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/lra.2022.3143219
- OpenAlex ID：https://openalex.org/W3195789010
- 落地页：https://doi.org/10.1109/lra.2022.3143219
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Autonomous Vehicle Technology and Safety, Adversarial Robustness in Machine Learning
- 关键词：Segmentation, Computer science, Software deployment, Metric (unit), Task (project management), Artificial intelligence, Image segmentation, Scale-space segmentation, Computer vision, Pattern recognition (psychology), Machine learning, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Semantic segmentation is an important task that helps autonomous vehicles understand their surroundings and navigate safely. However, during deployment, even the most mature segmentation models are vulnerable to various external factors that can degrade the segmentation performance with potentially catastrophic consequences for the vehicle and its surroundings. To address this issue, we propose a failure detection framework to identify pixel-level misclassification. We do so by exploiting internal features of the segmentation model and training it simultaneously with a failure detection network. During deployment, the failure detector flags areas in the image where the segmentation model has failed to segment correctly. We evaluate the proposed approach against state-of-the-art methods and achieve 12.30%, 9.46%, and 9.65% performance improvement in the AUPR-Error metric for Cityscapes, BDD100k, and Mapillary semantic segmentation datasets.

## 16574. Interpretability-Guided Defense Against Backdoor Attacks to Deep Neural Networks

- 标题：Interpretability-Guided Defense Against Backdoor Attacks to Deep Neural Networks
- 作者：Wei Jiang, Xiangyu Wen, Jinyu Zhan, Xupeng Wang, Ziwei Song
- 年份：2021
- 出版日期：2021-09-08
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Computer-Aided Design of Integrated Circuits and Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0278-0070
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcad.2021.3111123
- OpenAlex ID：https://openalex.org/W3196546979
- 落地页：https://doi.org/10.1109/tcad.2021.3111123
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Domain Adaptation and Few-Shot Learning, Anomaly Detection Techniques and Applications
- 关键词：Backdoor, Interpretability, Computer science, Deep neural networks, Pruning, Artificial neural network, Artificial intelligence, Machine learning, Computer security, Biology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
As an emerging threat to deep neural networks (DNNs), backdoor attacks have received increasing attentions due to the challenges posed by the lack of transparency inherent in DNNs. In this article, we develop an efficient algorithm from the interpretability of DNNs to defend against backdoor attacks to DNN models. To extract critical neurons, we deploy sets of control gates following neurons in layers, and the function of a DNN model can be interpreted as semantic sensitivities of neurons to input samples. A backdoor identification approach, derived from the activation frequency distribution on critical neurons, is proposed to reveal anomalies of particular neurons produced by backdoor attacks. Subsequently, a feasible and fine-grained pruning strategy is introduced to eliminate backdoors hidden in DNN models, without the need of retraining. Extensive experiments demonstrate that the proposed algorithm can identify and eliminate malicious backdoors efficiently in both single-target and multitarget scenarios with the performance of a DNN model retained to a large extent.

## 16575. Hybrid Gradient Descent Grey Wolf Optimizer for Optimal Feature Selection

- 标题：Hybrid Gradient Descent Grey Wolf Optimizer for Optimal Feature Selection
- 作者：Peter Mule Kitonyi, Davies Segera
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：BioMed Research International
- 来源类型：journal
- 出版方：Hindawi Publishing Corporation
- ISSN-L：2314-6133
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1155/2021/2555622
- OpenAlex ID：https://openalex.org/W3197763142
- 落地页：https://doi.org/10.1155/2021/2555622
- 开放 PDF 链接：https://downloads.hindawi.com/journals/bmri/2021/2555622.pdf
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Machine Learning and Data Classification, Machine Learning and ELM
- 关键词：Feature selection, Gradient descent, Feature (linguistics), Computer science, Particle swarm optimization, Binary number, Selection (genetic algorithm), Artificial intelligence, Data mining, Pattern recognition (psychology), Algorithm, Mathematics, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
-measure, accuracy, precision, and sensitivity. The proposed optimizer outperformed the three other optimizers in 3 of the 6 datasets in average metrics. The proposed optimizer showed promise in its capability to balance the two objectives in feature selection and could be further enhanced.

## 16576. Atom correlation based graph propagation for scene graph generation

- 标题：Atom correlation based graph propagation for scene graph generation
- 作者：Bingqian Lin, Yi Zhu, Xiaodan Liang
- 年份：2021
- 出版日期：2021-09-03
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2021.108300
- OpenAlex ID：https://openalex.org/W3198555355
- 落地页：https://doi.org/10.1016/j.patcog.2021.108300
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Advanced Graph Neural Networks
- 关键词：Computer science, Graph, Correlation, Scene graph, Artificial intelligence, Theoretical computer science, Knowledge graph, Pattern recognition (psychology), Task (project management), Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16577. A visual persistence model for image captioning

- 标题：A visual persistence model for image captioning
- 作者：Yiyu Wang, Jungang Xu, Yingfei Sun
- 年份：2021
- 出版日期：2021-10-07
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2021.10.014
- OpenAlex ID：https://openalex.org/W3203243482
- 落地页：https://doi.org/10.1016/j.neucom.2021.10.014
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Closed captioning, Computer science, Pooling, Object (grammar), Persistence (discontinuity), Feature (linguistics), Artificial intelligence, Word (group theory), Encoder, Representation (politics), Visualization, Computer vision, Image (mathematics), Natural language processing, Pattern recognition (psychology), Speech recognition, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16578. End-to-End Supermask Pruning: Learning to Prune Image Captioning Models

- 标题：End-to-End Supermask Pruning: Learning to Prune Image Captioning Models
- 作者：Jia Huei Tan, Chee Seng Chan, Joon Huang Chuah
- 年份：2021
- 出版日期：2021-10-06
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.patcog.2021.108366
- OpenAlex ID：https://openalex.org/W3203553414
- 落地页：https://doi.org/10.1016/j.patcog.2021.108366
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning, Advanced Image and Video Retrieval Techniques
- 关键词：Closed captioning, Computer science, Pruning, Encoder, Transformer, Artificial intelligence, Deep learning, Language model, Code (set theory), Image (mathematics), Pattern recognition (psychology), Machine learning, Speech recognition
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16579. Empathetic Response Generation through Graph-based Multi-hop Reasoning on Emotional Causality

- 标题：Empathetic Response Generation through Graph-based Multi-hop Reasoning on Emotional Causality
- 作者：Jiashuo Wang, Wenjie Li, Peiqin Lin, Feiteng Mu
- 年份：2021
- 出版日期：2021-10-01
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.knosys.2021.107547
- OpenAlex ID：https://openalex.org/W3204746395
- 落地页：https://doi.org/10.1016/j.knosys.2021.107547
- 主主题：Topic Modeling
- 主题：Topic Modeling, Multimodal Machine Learning Applications, Artificial Intelligence in Games
- 关键词：Causality (physics), Computer science, Causal reasoning, Hop (telecommunications), Psychology, Cognitive psychology, Social psychology, Theoretical computer science, Cognition, Computer network, Neuroscience
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16580. Textual Backdoor Attack for the Text Classification System

- 标题：Textual Backdoor Attack for the Text Classification System
- 作者：Hyun Kwon, Sanghyun Lee
- 年份：2021
- 出版日期：2021-10-22
- 类型：article
- 语言：en
- 来源：Security and Communication Networks
- 来源类型：journal
- 出版方：Hindawi Publishing Corporation
- ISSN-L：1939-0114
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1155/2021/2938386
- OpenAlex ID：https://openalex.org/W3205191765
- 落地页：https://doi.org/10.1155/2021/2938386
- 开放 PDF 链接：https://downloads.hindawi.com/journals/scn/2021/2938386.pdf
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Network Security and Intrusion Detection
- 关键词：Backdoor, Computer science, Sentence, Artificial intelligence, Speech recognition, Pattern recognition (psychology), Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep neural networks provide good performance for image recognition, speech recognition, text recognition, and pattern recognition. However, such networks are vulnerable to backdoor attacks. In a backdoor attack, normal data that do not include a specific trigger are correctly classified by the target model, but backdoor data that include the trigger are incorrectly classified by the target model. One advantage of a backdoor attack is that the attacker can use a specific trigger to attack at a desired time. In this study, we propose a backdoor attack targeting the BERT model, which is a classification system designed for use in the text domain. Under the proposed method, the model is additionally trained on a backdoor sentence that includes a specific trigger, and afterward, if the trigger is attached before or after an original sentence, it will be misclassified by the model. In our experimental evaluation, we used two movie review datasets (MR and IMDB). The results show that using the trigger word “ATTACK” at the beginning of an original sentence, the proposed backdoor method had a 100% attack success rate when approximately 1.0% and 0.9% of the training data consisted of backdoor samples, and it allowed the model to maintain an accuracy of 86.88% and 90.80% on the original samples in the MR and IMDB datasets, respectively.

## 16581. Defending Deep Neural Networks Against Backdoor Attack by Using De-Trigger Autoencoder

- 标题：Defending Deep Neural Networks Against Backdoor Attack by Using De-Trigger Autoencoder
- 作者：Hyun Kwon
- 年份：2021
- 出版日期：2021-10-19
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2021.3086529
- OpenAlex ID：https://openalex.org/W3206218040
- 落地页：https://doi.org/10.1109/access.2021.3086529
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/6514899/09579062.pdf
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Anomaly Detection Techniques and Applications
- 关键词：Backdoor, MNIST database, Autoencoder, Computer science, Artificial intelligence, Artificial neural network, Deep learning, Pattern recognition (psychology), Sample (material), Machine learning, Computer security, Physics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A backdoor attack is a method that causes misrecognition in a deep neural network by training it on additional data that have a specific trigger. The network will correctly recognize normal samples (which lack the specific trigger) as their proper classes but will misrecognize backdoor samples (which contain the trigger) as target classes. In this paper, I propose a method of defense against backdoor attacks that uses a de-trigger autoencoder. In the proposed scheme, the trigger in the backdoor sample is removed using the de-trigger autoencoder, and the backdoor sample is detected from the change in the classification result. Experiments were conducted using MNIST, Fashion-MNIST, and CIFAR-10 as the experimental datasets and TensorFlow as the machine learning library. For MNIST, Fashion-MNIST, and CIFAR-10, respectively, the proposed method detected 91.5%, 82.3%, and 90.9% of the backdoor samples and had 96.1%, 89.6%, and 91.2% accuracy on legitimate samples.

## 16582. Domain Generalization Via Encoding and Resampling in a Unified Latent Space

- 标题：Domain Generalization Via Encoding and Resampling in a Unified Latent Space
- 作者：Yajing Liu, Zhiwei Xiong, Ya Li, Xinmei Tian, Zheng-Jun Zha
- 年份：2021
- 出版日期：2021-10-20
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2021.3121564
- OpenAlex ID：https://openalex.org/W3207927571
- 落地页：https://doi.org/10.1109/tmm.2021.3121564
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Human Pose and Action Recognition
- 关键词：Computer science, Gaussian, Algorithm, Pattern recognition (psychology), Resampling, Generalizability theory, Regularization (linguistics), Feature vector, Artificial intelligence, Latent variable, Generalization, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Domain generalization aims to generalize a network trained on multiple domains to unknown yet related domains. Operating under the assumption that invariant information generalizes well to unknown domains, previous work has aimed to minimize the discrepancies amongst distributions across given domains. However, without prior regularization of feature distributions, the network in practice overfits the invariant information in the given domains. Moreover, if there are insufficient samples in given domains, then domain generalizability is limited, as diverse domain variations are not captured. To address these two drawbacks, we propose to explicitly map features in known and unknown domains onto latent space in a fixed Gaussian mixture distribution by variational coding. As a result, features in different classes follow Gaussian distributions with different mean values. The predefined latent space narrows discrepancies between known and unknown domains and effectively separates samples into different classes. Moreover, we propose to perturb sample features with gradients from the distribution regularized loss. This perturbation generates samples beyond but near the latent space of prior distributions, which has a profound impact on domain variations. Experiments and visualizations demonstrate the effectiveness of our proposed method.

## 16583. Online early terminated streaming feature selection based on Rough Set theory

- 标题：Online early terminated streaming feature selection based on Rough Set theory
- 作者：Peng Zhou, Peipei Li, Shu Zhao, Yanping Zhang
- 年份：2021
- 出版日期：2021-10-25
- 类型：article
- 语言：en
- 来源：Applied Soft Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1568-4946
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.asoc.2021.107993
- OpenAlex ID：https://openalex.org/W3208396386
- 落地页：https://doi.org/10.1016/j.asoc.2021.107993
- 主主题：Rough Sets and Fuzzy Logic
- 主题：Rough Sets and Fuzzy Logic, Machine Learning and Data Classification, Data Stream Mining Techniques
- 关键词：Feature selection, Computer science, Feature (linguistics), Dimensionality reduction, Curse of dimensionality, Artificial intelligence, Selection (genetic algorithm), Data mining, Function (biology), Machine learning, Set (abstract data type), Rough set
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16584. Learning Text-image Joint Embedding for Efficient Cross-modal Retrieval with Deep Feature Engineering

- 标题：Learning Text-image Joint Embedding for Efficient Cross-modal Retrieval with Deep Feature Engineering
- 作者：Zhongwei Xie, Ling Liu, Yanzhao Wu, Luo Zhong, Lin Li
- 年份：2021
- 出版日期：2021-12-01
- 类型：article
- 语言：en
- 来源：ACM Transactions on Information Systems
- 来源类型：journal
- ISSN-L：1046-8188
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1145/3490519
- OpenAlex ID：https://openalex.org/W3208601917
- 落地页：https://doi.org/10.1145/3490519
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications, Image Retrieval and Classification Techniques
- 关键词：Joint (building), Embedding, Modal, Feature (linguistics), Computer science, Artificial intelligence, Image (mathematics), Pattern recognition (psychology), Deep learning, Feature learning, Information retrieval, Image retrieval, Feature engineering, Engineering, Structural engineering, Materials science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This article introduces a two-phase deep feature engineering framework for efficient learning of semantics enhanced joint embedding, which clearly separates the deep feature engineering in data preprocessing from training the text-image joint embedding model. We use the Recipe1M dataset for the technical description and empirical validation. In preprocessing, we perform deep feature engineering by combining deep feature engineering with semantic context features derived from raw text-image input data. We leverage LSTM to identify key terms, deep NLP models from the BERT family, TextRank, or TF-IDF to produce ranking scores for key terms before generating the vector representation for each key term by using Word2vec. We leverage Wide ResNet50 and Word2vec to extract and encode the image category semantics of food images to help semantic alignment of the learned recipe and image embeddings in the joint latent space. In joint embedding learning, we perform deep feature engineering by optimizing the batch-hard triplet loss function with soft-margin and double negative sampling, taking into account also the category-based alignment loss and discriminator-based alignment loss. Extensive experiments demonstrate that our SEJE approach with deep feature engineering significantly outperforms the state-of-the-art approaches.

## 16585. IWA: Integrated gradient‐based white‐box attacks for fooling deep neural networks

- 标题：IWA: Integrated gradient‐based white‐box attacks for fooling deep neural networks
- 作者：Yixiang Wang, Jiqiang Liu, Xiaolin Chang, Jelena Mišić, Vojislav B. Mišić
- 年份：2021
- 出版日期：2021-10-28
- 类型：article
- 语言：en
- 来源：International Journal of Intelligent Systems
- 来源类型：journal
- 出版方：Wiley
- ISSN-L：0884-8173
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1002/int.22720
- OpenAlex ID：https://openalex.org/W3209367351
- 落地页：https://doi.org/10.1002/int.22720
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Advanced Neural Network Applications
- 关键词：Adversarial system, Perturbation (astronomy), Computer science, Artificial neural network, Jacobian matrix and determinant, Deep neural networks, Algorithm, Artificial intelligence, Mathematics, Applied mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The widespread application of deep neural network (DNN) techniques is being challenged by adversarial examples—the legitimate input added with imperceptible and well-designed perturbation that can fool DNNs easily in the DNN testing/deploying stage. Previous white-box adversarial example generation algorithms used the Jacobian gradient information to add the perturbation. This imprecise and inexplicit information can cause unnecessary perturbation when generating adversarial examples. This paper aims to address this issue. We first propose to apply the more informative and distilled gradient information, namely, integrated gradient, to generate adversarial examples. To further make the perturbation more imperceptible, we propose to employ the restriction combination of L 0 and L 1 / L 2 second, which can restrict the total perturbation and the perturbation points simultaneously. Meanwhile, to address the nondifferentiable problem of L 1 , we explore a proximal operation of L 1 third. On the basis of these three works, we propose two Integrated gradient-based White-box Adversarial example generation algorithms (IWA): Integrated gradient-based Finite Point Attack (IFPA) and Integrated gradient-based Universe Attack (IUA). IFPA is suitable for situations where there are a determined number of points to be perturbed. IUA is suitable for situations where no perturbation point number is preset to obtain more adversarial examples. We verify the effectiveness of the proposed algorithms on both structured and unstructured data sets, and compare them with five baseline generation algorithms. The results show that our proposed algorithms craft adversarial examples with more imperceptible perturbation and satisfactory crafting rate. L 2 restriction is suitable for unstructured data sets and L 1 restriction performs better in the structured data set.

## 16586. Generating natural adversarial examples with universal perturbations for text classification

- 标题：Generating natural adversarial examples with universal perturbations for text classification
- 作者：Haoran Gao, Hua Zhang, Xingguo Yang, Wenmin Li, Fei Gao, Qiaoyan Wen
- 年份：2021
- 出版日期：2021-11-02
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2021.10.089
- OpenAlex ID：https://openalex.org/W3210431426
- 落地页：https://doi.org/10.1016/j.neucom.2021.10.089
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques
- 关键词：Adversarial system, Computer science, Artificial intelligence, Classifier (UML), Word (group theory), Theoretical computer science, Algorithm, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16587. VLDeformer: Vision–Language Decomposed Transformer for fast cross-modal retrieval

- 标题：VLDeformer: Vision–Language Decomposed Transformer for fast cross-modal retrieval
- 作者：Lisai Zhang, Hongfa Wu, Qingcai Chen, Yimeng Deng, Joanna Siebert, Zhonghua Li, Yunpeng Han, Dejiang Kong, Zhao Cao
- 年份：2022
- 出版日期：2022-07-04
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2022.109316
- OpenAlex ID：https://openalex.org/W3216333240
- 落地页：https://doi.org/10.1016/j.knosys.2022.109316
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Transformer, Computer science, Modal, Search engine indexing, Artificial intelligence, Encoder, Inference, Embedding, Pairwise comparison, Natural language processing, Pattern recognition (psychology), Speech recognition, Voltage, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16588. Optimal Deep Neural Network-Based Model for Answering Visual Medical Question

- 标题：Optimal Deep Neural Network-Based Model for Answering Visual Medical Question
- 作者：Karim Gasmi, Ibtihel Ben Ltaifa, Gaël Lejeune, Hamoud Alshammari, Lassaad Ben Ammar, Mahmood A. Mahmood
- 年份：2021
- 出版日期：2021-12-28
- 类型：article
- 语言：en
- 来源：Cybernetics & Systems
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0196-9722
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1080/01969722.2021.2018543
- OpenAlex ID：https://openalex.org/W4200048628
- 落地页：https://doi.org/10.1080/01969722.2021.2018543
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Artificial intelligence, Deep learning, Question answering, Context (archaeology), Machine learning, Artificial neural network, Set (abstract data type)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Over the last few years, the amount of available information has increased exponentially in all professional fields, including the medical field. Modern-day patients have access to a wealth of medical information, whether it be from brochures, newspapers, television campaigns, or internet documents. To facilitate and accelerate the search for medical information, more precise systems have been implemented, such as visual question-and-answer systems. A visual question-and-answer system is designed to provide direct and precise answers to questions asked in natural language. In this context, we propose an optimal deep neural network model based on an adaptive optimization algorithm, which takes medical images and natural language questions as input, then provides precise answers as output. Our model starts by classifying medical questions following an embedding phase. We then use a deep learning model for visual and textual feature extraction and emergence. In this paper, we aim to maximize the accuracy rate and minimize the number of epochs in order to accelerate the process. This is a multi-objective optimization problem. The selection of deep learning model parameters, such as epoch number and batch size, is an essential step in improving the model, thus, we use an adaptive genetic algorithm to determine the optimal deep learning parameters. Finally, we propose a dense layer for answer retrieval. To evaluate our model, we used the ImageCLEF 2019 VQA data set. Our model outperforms existing visual question-and-answer systems and offers a significantly higher retrieval accuracy rate.

## 16589. SSL++: Improving Self-Supervised Learning by Mitigating the Proxy Task-Specificity Problem

- 标题：SSL++: Improving Self-Supervised Learning by Mitigating the Proxy Task-Specificity Problem
- 作者：Chen Song, Jing‐Hao Xue, Jianlong Chang, Jianzhong Zhang, Jufeng Yang, Qi Tian
- 年份：2021
- 出版日期：2021-12-21
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tip.2021.3135470
- OpenAlex ID：https://openalex.org/W4200312714
- 落地页：https://doi.org/10.1109/tip.2021.3135470
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Human Pose and Action Recognition
- 关键词：Computer science, Generalizability theory, Leverage (statistics), Artificial intelligence, Machine learning, Proxy (statistics), Natural language processing, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The success of deep convolutional networks (ConvNets) generally relies on a massive amount of well-labeled data, which is labor-intensive and time-consuming to collect and annotate in many scenarios. To eliminate such limitation, self-supervised learning (SSL) is recently proposed. Specifically, by solving a pre-designed proxy task, SSL is capable of capturing general-purpose features without requiring human supervision. Existing efforts focus obsessively on designing a particular proxy task but ignore the semanticity of samples that are advantageous to downstream tasks, resulting in the inherent limitation that the learned features are specific to the proxy task, namely the proxy task-specificity of features. In this work, to improve the generalizability of features learned by existing SSL methods, we present a novel self-supervised framework SSL++ to incorporate the proxy task-independent semanticity of samples into the representation learning process. Technically, SSL++ aims to leverage the complementarity, between the low-level generic features learned by a proxy task and the high-level semantic features newly learned by the generated semantic pseudo-labels, to mitigate the task-specificity and improve the generalizability of features. Extensive experiments show that SSL++ performs favorably against the state-of-the-art approaches on the established and latest SSL benchmarks.

## 16590. A comparative study of quantum support vector machine algorithm for handwritten recognition with support vector machine algorithm

- 标题：A comparative study of quantum support vector machine algorithm for handwritten recognition with support vector machine algorithm
- 作者：Anurag Rana, Pankaj Vaidya, Gaurav Gupta
- 年份：2021
- 出版日期：2021-12-04
- 类型：article
- 语言：en
- 来源：Materials Today Proceedings
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2214-7853
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.matpr.2021.11.350
- OpenAlex ID：https://openalex.org/W4200618837
- 落地页：https://doi.org/10.1016/j.matpr.2021.11.350
- 主主题：Handwritten Text Recognition Techniques
- 主题：Handwritten Text Recognition Techniques, Machine Learning and Algorithms, Quantum Computing Algorithms and Architecture
- 关键词：Support vector machine, Computer science, Algorithm, Quantum machine learning, Speedup, Variety (cybernetics), Quantum, Quantum algorithm, Quantum computer, Identification (biology), Machine learning, Artificial intelligence, Parallel computing
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16591. LIME-Based Data Selection Method for SAR Images Generation Using GAN

- 标题：LIME-Based Data Selection Method for SAR Images Generation Using GAN
- 作者：Mingzhe Zhu, Bo Zang, Linlin Ding, Tao Lei, Zhenpeng Feng, Jingyuan Fan
- 年份：2022
- 出版日期：2022-01-03
- 类型：article
- 语言：en
- 来源：Remote Sensing
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2072-4292
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/rs14010204
- OpenAlex ID：https://openalex.org/W4206103415
- 落地页：https://doi.org/10.3390/rs14010204
- 开放 PDF 链接：https://www.mdpi.com/2072-4292/14/1/204/pdf?version=1641278966
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Adversarial Robustness in Machine Learning, Generative Adversarial Networks and Image Synthesis
- 关键词：Computer science, Artificial intelligence, Synthetic aperture radar, Spurious relationship, Pattern recognition (psychology), Classifier (UML), Computer vision, Image (mathematics), Generative grammar, Pixel, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep learning has obtained remarkable achievements in computer vision, especially image and video processing. However, in synthetic aperture radar (SAR) image recognition, the application of DNNs is usually restricted due to data insufficiency. To augment datasets, generative adversarial networks (GANs) are usually used to generate numerous photo-realistic SAR images. Although there are many pixel-level metrics to measure GAN’s performance from the quality of generated SAR images, there are few measurements to evaluate whether the generated SAR images include the most representative features of the target. In this case, the classifier probably categorizes a SAR image into the corresponding class based on “wrong” criterion, i.e., “Clever Hans”. In this paper, local interpretable model-agnostic explanation (LIME) is innovatively utilized to evaluate whether a generated SAR image possessed the most representative features of a specific kind of target. Firstly, LIME is used to visualize positive contributions of the input SAR image to the correct prediction of the classifier. Subsequently, these representative SAR images can be selected handily by evaluating how much the positive contribution region matches the target. Experimental results demonstrate that the proposed method can ally “Clever Hans” phenomenon greatly caused by the spurious relationship between generated SAR images and the corresponding classes.

## 16592. Multiple weak supervision for short text classification

- 标题：Multiple weak supervision for short text classification
- 作者：Li-Ming Chen, Baoxin Xiu, Zhaoyun Ding
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：en
- 来源：Applied Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0924-669X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s10489-021-02958-3
- OpenAlex ID：https://openalex.org/W4206256100
- 落地页：https://doi.org/10.1007/s10489-021-02958-3
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s10489-021-02958-3.pdf
- 主主题：Text and Document Classification Technologies
- 主题：Text and Document Classification Technologies, Imbalanced Data Classification Techniques, Machine Learning and Data Classification
- 关键词：Computer science, Cluster analysis, Labeled data, Probabilistic logic, Recall, Machine learning, Artificial intelligence, Precision and recall, F1 score, Data mining, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract For short text classification, insufficient labeled data, data sparsity, and imbalanced classification have become three major challenges. For this, we proposed multiple weak supervision, which can label unlabeled data automatically. Different from prior work, the proposed method can generate probabilistic labels through conditional independent model. What’s more, experiments were conducted to verify the effectiveness of multiple weak supervision. According to experimental results on public dadasets, real datasets and synthetic datasets, unlabeled imbalanced short text classification problem can be solved effectively by multiple weak supervision. Notably, without reducing precision , recall , and F1-score can be improved by adding distant supervision clustering, which can be used to meet different application needs.

## 16593. Word-Region Alignment-Guided Multimodal Neural Machine Translation

- 标题：Word-Region Alignment-Guided Multimodal Neural Machine Translation
- 作者：Yuting Zhao, Mamoru Komachi, Tomoyuki Kajiwara, Chenhui Chu
- 年份：2021
- 出版日期：2021-12-28
- 类型：article
- 语言：en
- 来源：IEEE/ACM Transactions on Audio Speech and Language Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2329-9290
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1109/taslp.2021.3138719
- OpenAlex ID：https://openalex.org/W4206588072
- 落地页：https://doi.org/10.1109/taslp.2021.3138719
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6570655/9657755/09664333.pdf
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Natural Language Processing Techniques, Topic Modeling
- 关键词：Computer science, Machine translation, Natural language processing, Artificial intelligence, Leverage (statistics), Transformer, Modalities, Test set, Task (project management), Speech recognition
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We propose word-region alignment-guided multimodal neural machine translation (MNMT), a novel model for MNMT that links the semantic correlation between textual and visual modalities using word-region alignment (WRA). Existing studies on MNMT have mainly focused on the effect of integrating visual and textual modalities. However, they do not leverage the semantic relevance between the two modalities. We advance the semantic correlation between textual and visual modalities in MNMT by incorporating WRA as a bridge. This proposal has been implemented on two mainstream architectures of neural machine translation (NMT): the recurrent neural network (RNN) and the transformer. Experiments on two public benchmarks, English–German and English–French translation tasks using the Multi30k dataset and English–Japanese translation tasks using the Flickr30kEnt-JP dataset prove that our model has a significant improvement with respect to the competitive baselines across different evaluation metrics and outperforms most of the existing MNMT models. For example, 1.0 BLEU scores are improved for the English–German task and 1.1 BLEU scores are improved for the English–French task on the Multi30k test2016 set; and 0.7 BLEU scores are improved for the English–Japanese task on the Flickr30kEnt-JP test set. Further analysis demonstrates that our model can achieve better translation performance by integrating WRA, leading to better visual information use.

## 16594. Defense against local model poisoning attacks to byzantine-robust federated learning

- 标题：Defense against local model poisoning attacks to byzantine-robust federated learning
- 作者：Shiwei Lu, Ruihu Li, Xuan Chen, Yuena Ma
- 年份：2022
- 出版日期：2022-01-27
- 类型：article
- 语言：en
- 来源：Frontiers of Computer Science
- 来源类型：journal
- 出版方：Higher Education Press
- ISSN-L：2095-2228
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11704-021-1067-4
- OpenAlex ID：https://openalex.org/W4210432793
- 落地页：https://doi.org/10.1007/s11704-021-1067-4
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Privacy-Preserving Technologies in Data
- 关键词：Computer science, Byzantine architecture, Computer security, Scheme (mathematics), Federated learning, Artificial intelligence, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16595. Verification of integrity of deployed deep learning models using Bayesian Optimization

- 标题：Verification of integrity of deployed deep learning models using Bayesian Optimization
- 作者：Deepthi Praveenlal Kuttichira, Sunil Gupta, Dang Nguyen, Santu Rana, Svetha Venkatesh
- 年份：2022
- 出版日期：2022-01-25
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.knosys.2022.108238
- OpenAlex ID：https://openalex.org/W4210466755
- 落地页：https://doi.org/10.1016/j.knosys.2022.108238
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Neural Network Applications, Machine Learning and Data Classification
- 关键词：Computer science, Cloud computing, Autoencoder, Artificial intelligence, Bayesian optimization, Machine learning, Sample (material), Deep learning, Optimization problem, Upload, Data mining, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16596. Differentially private self-normalizing neural networks for adversarial robustness in federated learning

- 标题：Differentially private self-normalizing neural networks for adversarial robustness in federated learning
- 作者：Olakunle Ibitoye, M. Omair Shafiq, Ashraf Matrawy
- 年份：2022
- 出版日期：2022-01-29
- 类型：article
- 语言：en
- 来源：Computers & Security
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-4048
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.cose.2022.102631
- OpenAlex ID：https://openalex.org/W4210517555
- 落地页：https://doi.org/10.1016/j.cose.2022.102631
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Adversarial Robustness in Machine Learning, Cryptography and Data Security
- 关键词：Adversarial system, Computer science, Differential privacy, Artificial intelligence, Machine learning, Federated learning, Robustness (evolution), Artificial neural network, Normalization (sociology), Deep neural networks, Computer security, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16597. Sample complexity of learning parametric quantum circuits

- 标题：Sample complexity of learning parametric quantum circuits
- 作者：Haoyuan Cai, Qi Ye, Dong-Ling Deng
- 年份：2022
- 出版日期：2022-01-26
- 类型：article
- 语言：en
- 来源：Quantum Science and Technology
- 来源类型：journal
- 出版方：IOP Publishing
- ISSN-L：2058-9565
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1088/2058-9565/ac4f30
- OpenAlex ID：https://openalex.org/W4210728928
- 落地页：https://doi.org/10.1088/2058-9565/ac4f30
- 主主题：Quantum Computing Algorithms and Architecture
- 主题：Quantum Computing Algorithms and Architecture, Machine Learning and Algorithms
- 关键词：Algorithm, Computer science, Artificial intelligence, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Quantum computers hold unprecedented potentials for machine learning applications. Here, we prove that physical quantum circuits are probably approximately correct learnable on a quantum computer via empirical risk minimization: to learn a parametric quantum circuit with at most n c gates and each gate acting on a constant number of qubits, the sample complexity is bounded by <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" display="inline" overflow="scroll"> <mml:mrow> <mml:mover accent="true"> <mml:mrow> <mml:mi>O</mml:mi> </mml:mrow> <mml:mo>~</mml:mo> </mml:mover> </mml:mrow> <mml:mrow> <mml:mo stretchy="false">(</mml:mo> <mml:mrow> <mml:msup> <mml:mrow> <mml:mi>n</mml:mi> </mml:mrow> <mml:mrow> <mml:mi>c</mml:mi> <mml:mo>+</mml:mo> <mml:mn>1</mml:mn> </mml:mrow> </mml:msup> </mml:mrow> <mml:mo stretchy="false">)</mml:mo> </mml:mrow> </mml:math> . In particular, we explicitly construct a family of variational quantum circuits with O ( n c +1 ) elementary gates arranged in a fixed pattern, which can represent all physical quantum circuits consisting of at most n c elementary gates. Our results provide a valuable guide for quantum machine learning in both theory and practice.

## 16598. Continual Learning Objective for Analyzing Complex Knowledge Representations

- 标题：Continual Learning Objective for Analyzing Complex Knowledge Representations
- 作者：Asad Mansoor Khan, Taimur Hassan, Muhammad Usman Akram, Norah Saleh Alghamdi, Naoufel Werghi
- 年份：2022
- 出版日期：2022-02-21
- 类型：article
- 语言：en
- 来源：Sensors
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1424-8220
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/s22041667
- OpenAlex ID：https://openalex.org/W4212822980
- 落地页：https://doi.org/10.3390/s22041667
- 开放 PDF 链接：https://www.mdpi.com/1424-8220/22/4/1667/pdf?version=1645433754
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Advanced Neural Network Applications
- 关键词：Forgetting, Computer science, Artificial intelligence, Machine learning, Exploit, Process (computing), Deep learning, Vendor, Cognitive psychology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Human beings tend to incrementally learn from the rapidly changing environment without comprising or forgetting the already learned representations. Although deep learning also has the potential to mimic such human behaviors to some extent, it suffers from catastrophic forgetting due to which its performance on already learned tasks drastically decreases while learning about newer knowledge. Many researchers have proposed promising solutions to eliminate such catastrophic forgetting during the knowledge distillation process. However, to our best knowledge, there is no literature available to date that exploits the complex relationships between these solutions and utilizes them for the effective learning that spans over multiple datasets and even multiple domains. In this paper, we propose a continual learning objective that encompasses mutual distillation loss to understand such complex relationships and allows deep learning models to effectively retain the prior knowledge while adapting to the new classes, new datasets, and even new applications. The proposed objective was rigorously tested on nine publicly available, multi-vendor, and multimodal datasets that span over three applications, and it achieved the top-1 accuracy of 0.9863% and an F1-score of 0.9930.

## 16599. EF-Train: Enable Efficient On-device CNN Training on FPGA through Data Reshaping for Online Adaptation or Personalization

- 标题：EF-Train: Enable Efficient On-device CNN Training on FPGA through Data Reshaping for Online Adaptation or Personalization
- 作者：Yue Tang, Xinyi Zhang, Peipei Zhou, Jingtong Hu
- 年份：2022
- 出版日期：2022-02-24
- 类型：article
- 语言：en
- 来源：ACM Transactions on Design Automation of Electronic Systems
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1084-4309
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/3505633
- OpenAlex ID：https://openalex.org/W4213446428
- 落地页：https://doi.org/10.1145/3505633
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Domain Adaptation and Few-Shot Learning, Adversarial Robustness in Machine Learning
- 关键词：Computer science, FLOPS, Field-programmable gate array, Edge device, Efficient energy use, Schedule, Enhanced Data Rates for GSM Evolution, Personalization, Edge computing, Throughput, Lookup table, Embedded system, Cloud computing, Parallel computing, Artificial intelligence, Wireless, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Conventionally, DNN models are trained once in the cloud and deployed in edge devices such as cars, robots, or unmanned aerial vehicles (UAVs) for real-time inference. However, there are many cases that require the models to adapt to new environments, domains, or users. In order to realize such domain adaption or personalization, the models on devices need to be continuously trained on the device. In this work, we design EF-Train, an efficient DNN training accelerator with a unified channel-level parallelism-based convolution kernel that can achieve end-to-end training on resource-limited low-power edge-level FPGAs. It is challenging to implement on-device training on resource-limited FPGAs due to the low efficiency caused by different memory access patterns among forward and backward propagation and weight update. Therefore, we developed a data reshaping approach with intra-tile continuous memory allocation and weight reuse. An analytical model is established to automatically schedule computation and memory resources to achieve high energy efficiency on edge FPGAs. The experimental results show that our design achieves 46.99 GFLOPS and 6.09 GFLOPS/W in terms of throughput and energy efficiency, respectively.

## 16600. A Novel Multi-Sample Generation Method for Adversarial Attacks

- 标题：A Novel Multi-Sample Generation Method for Adversarial Attacks
- 作者：Mingxing Duan, Kenli Li, Jiayan Deng, Bin Xiao, Qi Tian
- 年份：2022
- 出版日期：2022-03-04
- 类型：article
- 语言：en
- 来源：ACM Transactions on Multimedia Computing Communications and Applications
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1551-6857
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/3506852
- OpenAlex ID：https://openalex.org/W4214893179
- 落地页：https://doi.org/10.1145/3506852
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Advanced Malware Detection Techniques
- 关键词：Computer science, Adversarial system, Black box, Sample (material), Robustness (evolution), Artificial intelligence, Deep learning, MNIST database, Generalization, Machine learning, Generator (circuit theory), Deconvolution, White box, Data mining, Algorithm, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep learning models are widely used in daily life, which bring great convenience to our lives, but they are vulnerable to attacks. How to build an attack system with strong generalization ability to test the robustness of deep learning systems is a hot issue in current research, among which the research on black-box attacks is extremely challenging. Most current research on black-box attacks assumes that the input dataset is known. However, in fact, it is difficult for us to obtain detailed information for those datasets. In order to solve the above challenges, we propose a multi-sample generation model for black-box model attacks, called MsGM. MsGM is mainly composed of three parts: multi-sample generation, substitute model training, and adversarial sample generation and attack. Firstly, we design a multi-task generation model to learn the distribution of the original dataset. The model first converts an arbitrary signal of a certain distribution into the shared features of the original dataset through deconvolution operations, and then according to different input conditions, multiple identical sub-networks generate the corresponding targeted samples. Secondly, the generated sample features achieve different outputs through querying the black-box model and training the substitute model, which are used to construct different loss functions to optimize and update the generator and substitute model. Finally, some common white-box attack methods are used to attack the substitute model to generate corresponding adversarial samples, which are utilized to attack the black-box model. We conducted a large number of experiments on the MNIST and CIFAR-10 datasets. The experimental results show that under the same settings and attack algorithms, MsGM achieves better performance than the based models.

## 16601. Layerwise Security Protection for Deep Neural Networks in Industrial Cyber Physical Systems

- 标题：Layerwise Security Protection for Deep Neural Networks in Industrial Cyber Physical Systems
- 作者：Wei Jiang, Ziwei Song, Jinyu Zhan, Di Liu, Jiafu Wan
- 年份：2022
- 出版日期：2022-03-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Industrial Informatics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1551-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tii.2022.3155112
- OpenAlex ID：https://openalex.org/W4214946748
- 落地页：https://doi.org/10.1109/tii.2022.3155112
- 主主题：Physical Unclonable Functions (PUFs) and Hardware Security
- 主题：Physical Unclonable Functions (PUFs) and Hardware Security, Adversarial Robustness in Machine Learning, Radiation Effects in Electronics
- 关键词：Computer science, Field-programmable gate array, Artificial neural network, Confidentiality, Encryption, Physical layer, Constraint (computer-aided design), Distributed computing, Computer engineering, Embedded system, Computer network, Computer security, Artificial intelligence, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Although deep neural networks (DNNs) have been increasingly applied in industrial cyber physical systems (ICPSs), they are vulnerable to security attacks due to the tight interaction between cyber elements and physical elements. In this article, we aim to protect the core IP of DNNs, i.e., the model weights, against security attacks. Different from conventional approaches, a layerwise protection framework is proposed to ensure the confidentiality of DNN model weights during the inference procedure such that the security quality is maximized, while satisfying the latency constraint of the DNN task. Based on the layerwise execution characteristics of DNN tasks, the encrypted layer-related weights are decrypted and fed to the next layer of DNN in plaintext. CPU-field programmable gate array (FPGA) coscheduling is considered to accelerate the execution of confidentiality protection, where CPU is utilized to conduct the decryption of weights and FPGA is used to perform the layer execution of DNN. Considering to provide optimal confidential protection for each layer, the problem is transformed into a quality of security maximization problem subject to layerwise execution constraint and deadline constraint of the DNN application. Due to the problem being NP-hard, a fast approximation algorithm is proposed to obtain the near-optimal solution under given real-time and security constraints. Extensive experiments and a real-life ICPS application evaluate the efficiency of the proposed techniques.

## 16602. Evolving CNN with Paddy Field Algorithm for Geographical Landmark Recognition

- 标题：Evolving CNN with Paddy Field Algorithm for Geographical Landmark Recognition
- 作者：Kanishk Bansal, Amar Singh, Sahil Verma, Kavita Kavita, N. Z. Jhanjhi, Mohammad Shorfuzzaman, Mehedi Masud
- 年份：2022
- 出版日期：2022-03-29
- 类型：article
- 语言：en
- 来源：Electronics
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2079-9292
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/electronics11071075
- OpenAlex ID：https://openalex.org/W4220748620
- 落地页：https://doi.org/10.3390/electronics11071075
- 开放 PDF 链接：https://www.mdpi.com/2079-9292/11/7/1075/pdf?version=1648717306
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Machine Learning and Data Classification, Smart Agriculture and AI
- 关键词：Hyperparameter, Computer science, Convolutional neural network, Benchmark (surveying), Artificial intelligence, Task (project management), Field (mathematics), Machine learning, Landmark, Deep learning, Pattern recognition (psychology), Architecture, Engineering, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Convolutional Neural Networks (CNNs) operate within a wide variety of hyperparameters, the optimization of which can greatly improve the performance of CNNs when performing the task at hand. However, these hyperparameters can be very difficult to optimize, either manually or by brute force. Neural architecture search or NAS methods have been developed to address this problem and are used to find the best architectures for the deep learning paradigm. In this article, a CNN has been evolved with a well-known nature-inspired metaheuristic paddy field algorithm (PFA). It can be seen that PFA can evolve the neural architecture using the Google Landmarks Dataset V2, which is one of the toughest datasets available in the literature. The CNN’s performance, when evaluated based on the accuracy benchmark, increases from an accuracy of 0.53 to 0.76, which is an improvement of more than 40%. The evolved architecture also shows some major improvements in hyperparameters that are normally considered to be the best suited for the task.

## 16603. A few-shot fine-grained image classification method leveraging global and local structures

- 标题：A few-shot fine-grained image classification method leveraging global and local structures
- 作者：Siyu Cao, Wen Wang, Jing Zhang, Min Zheng, Qingyong Li
- 年份：2022
- 出版日期：2022-03-05
- 类型：article
- 语言：en
- 来源：International Journal of Machine Learning and Cybernetics
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1868-8071
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s13042-022-01522-w
- OpenAlex ID：https://openalex.org/W4220752330
- 落地页：https://doi.org/10.1007/s13042-022-01522-w
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Advanced Neural Network Applications, Multimodal Machine Learning Applications
- 关键词：Discriminative model, Computer science, Artificial intelligence, Pattern recognition (psychology), Class (philosophy), Shot (pellet), Image (mathematics), Focus (optics), Contextual image classification, Computational intelligence, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16604. Relevance, redundancy, and complementarity trade-off (RRCT): A principled, generic, robust feature-selection tool

- 标题：Relevance, redundancy, and complementarity trade-off (RRCT): A principled, generic, robust feature-selection tool
- 作者：Athanasios Tsanas
- 年份：2022
- 出版日期：2022-03-31
- 类型：article
- 语言：en
- 来源：Patterns
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2666-3899
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1016/j.patter.2022.100471
- OpenAlex ID：https://openalex.org/W4220790242
- 落地页：https://doi.org/10.1016/j.patter.2022.100471
- 开放 PDF 链接：http://www.cell.com/article/S2666389922000514/pdf
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Machine Learning and Data Classification, Text and Document Classification Technologies
- 关键词：Redundancy (engineering), Complementarity (molecular biology), Feature selection, Computer science, Generalizability theory, Artificial intelligence, Minimum redundancy feature selection, Data mining, Pattern recognition (psychology), Machine learning, Theoretical computer science, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We present a new heuristic feature-selection (FS) algorithm that integrates in a principled algorithmic framework the three key FS components: relevance, redundancy, and complementarity. Thus, we call it relevance, redundancy, and complementarity trade-off (RRCT). The association strength between each feature and the response and between feature pairs is quantified via an information theoretic transformation of rank correlation coefficients, and the feature complementarity is quantified using partial correlation coefficients. We empirically benchmark the performance of RRCT against 19 FS algorithms across four synthetic and eight real-world datasets in indicative challenging settings evaluating the following: (1) matching the true feature set and (2) out-of-sample performance in binary and multi-class classification problems when presenting selected features into a random forest. RRCT is very competitive in both tasks, and we tentatively make suggestions on the generalizability and application of the best-performing FS algorithms across settings where they may operate effectively.

## 16605. I<sup>2</sup>Transformer: Intra- and Inter-Relation Embedding Transformer for TV Show Captioning

- 标题：I<sup>2</sup>Transformer: Intra- and Inter-Relation Embedding Transformer for TV Show Captioning
- 作者：Yunbin Tu, Liang Li, Li Su, Shengxiang Gao, Chenggang Yan, Zheng-Jun Zha, Zhengtao Yu, Qingming Huang
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2022.3159472
- OpenAlex ID：https://openalex.org/W4220863475
- 落地页：https://doi.org/10.1109/tip.2022.3159472
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Subtitles and Audiovisual Media, Video Analysis and Summarization
- 关键词：Closed captioning, Embedding, Transformer, Subtitle, Sentence, Generalization, Code (set theory)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Transformer achieves the state-of-the-art performance. We also evaluate the effectiveness of the IAE and IEE on two other relevant tasks of video with text inputs, i.e., TV show retrieval and video-guided machine translation. The encouraging performance further validates that the IAE and IEE blocks have a good generalization ability. The code is available at https://github.com/tuyunbin/I2Transformer.

## 16606. Cross-Domain Few-Shot Classification based on Lightweight Res2Net and Flexible GNN

- 标题：Cross-Domain Few-Shot Classification based on Lightweight Res2Net and Flexible GNN
- 作者：Yu Chen, Yunan Zheng, Zhenyu Xu, Tianhang Tang, Zixin Tang, Jie Chen, Yiguang Liu
- 年份：2022
- 出版日期：2022-03-24
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2022.108623
- OpenAlex ID：https://openalex.org/W4221131141
- 落地页：https://doi.org/10.1016/j.knosys.2022.108623
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Advanced Neural Network Applications
- 关键词：Metric (unit), Computer science, Domain (mathematical analysis), Encoder, Artificial intelligence, Feature (linguistics), Pattern recognition (psychology), Representation (politics), Residual, Function (biology), Block (permutation group theory), Shot (pellet), Data mining, Algorithm, Mathematics, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16607. The triggers that open the NLP model backdoors are hidden in the adversarial samples

- 标题：The triggers that open the NLP model backdoors are hidden in the adversarial samples
- 作者：Kun Shao, Yu Zhang, Junan Yang, Xiaoshuai Li, Hui Liu
- 年份：2022
- 出版日期：2022-04-18
- 类型：article
- 语言：en
- 来源：Computers & Security
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-4048
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.cose.2022.102730
- OpenAlex ID：https://openalex.org/W4224100994
- 落地页：https://doi.org/10.1016/j.cose.2022.102730
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Advanced Malware Detection Techniques
- 关键词：Computer science, Adversarial system, Artificial intelligence, Natural language processing, Speech recognition
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16608. Local Semantic Correlation Modeling Over Graph Neural Networks for Deep Feature Embedding and Image Retrieval

- 标题：Local Semantic Correlation Modeling Over Graph Neural Networks for Deep Feature Embedding and Image Retrieval
- 作者：Shichao Kan, Yigang Cen, Yang Li, Mladenovic Vladimir, Zhihai He
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2022.3163571
- OpenAlex ID：https://openalex.org/W4225665842
- 落地页：https://doi.org/10.1109/tip.2022.3163571
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Graph Neural Networks, Domain Adaptation and Few-Shot Learning
- 关键词：Pattern recognition (psychology), Discriminative model, Feature (linguistics), Embedding, Correlation, Image retrieval, Graph, Artificial neural network, Feature extraction
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep feature embedding aims to learn discriminative features or feature embeddings for image samples which can minimize their intra-class distance while maximizing their inter-class distance. Recent state-of-the-art methods have been focusing on learning deep neural networks with carefully designed loss functions. In this work, we propose to explore a new approach to deep feature embedding. We learn a graph neural network to characterize and predict the local correlation structure of images in the feature space. Based on this correlation structure, neighboring images collaborate with each other to generate and refine their embedded features based on local linear combination. Graph edges learn a correlation prediction network to predict the correlation scores between neighboring images. Graph nodes learn a feature embedding network to generate the embedded feature for a given image based on a weighted summation of neighboring image features with the correlation scores as weights. Our extensive experimental results under the image retrieval settings demonstrate that our proposed method outperforms the state-of-the-art methods by a large margin, especially for top-1 recalls.

## 16609. Birds of a Feather Flock Together: Category-Divergence Guidance for Domain Adaptive Segmentation

- 标题：Birds of a Feather Flock Together: Category-Divergence Guidance for Domain Adaptive Segmentation
- 作者：Bo Yuan, Danpei Zhao, Shuai Shao, Zehuan Yuan, Changhu Wang
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tip.2022.3162471
- OpenAlex ID：https://openalex.org/W4225773271
- 落地页：https://doi.org/10.1109/tip.2022.3162471
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, COVID-19 diagnosis using AI
- 关键词：Segmentation, Computer science, Artificial intelligence, Domain (mathematical analysis), Pattern recognition (psychology), Categorization, Feature (linguistics), Image segmentation, Matching (statistics), Computer vision, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Unsupervised domain adaptation (UDA) aims to enhance the generalization capability of a certain model from a source domain to a target domain. Present UDA models focus on alleviating the domain shift by minimizing the feature discrepancy between the source domain and the target domain but usually ignore the class confusion problem. In this work, we propose an Inter-class Separation and Intra-class Aggregation (ISIA) mechanism. It encourages the cross-domain representative consistency between the same categories and differentiation among diverse categories. In this way, the features belonging to the same categories are aligned together and the confusable categories are separated. By measuring the align complexity of each category, we design an Adaptive-weighted Instance Matching (AIM) strategy to further optimize the instance-level adaptation. Based on our proposed methods, we also raise a hierarchical unsupervised domain adaptation framework for cross-domain semantic segmentation task. Through performing the image-level, feature-level, category-level and instance-level alignment, our method achieves a stronger generalization performance of the model from the source domain to the target domain. In two typical cross-domain semantic segmentation tasks, i.e., GTA 5→ Cityscapes and SYNTHIA → Cityscapes, our method achieves the state-of-the-art segmentation accuracy. We also build two cross-domain semantic segmentation datasets based on the publicly available data, i.e., remote sensing building segmentation and road segmentation, for domain adaptive segmentation. Our code, models and datasets are available at https://github.com/HibiscusYB/BAFFT.

## 16610. COMET

- 标题：COMET
- 作者：Sian Jin, Chengming Zhang, Xintong Jiang, Yunhe Feng, Hui Guan, Guanpeng Li, Shuaiwen Leon Song, Dingwen Tao
- 年份：2021
- 出版日期：2021-12-01
- 类型：article
- 语言：en
- 来源：Proceedings of the VLDB Endowment
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：2150-8097
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.14778/3503585.3503597
- OpenAlex ID：https://openalex.org/W4226196214
- 落地页：https://doi.org/10.14778/3503585.3503597
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Adversarial Robustness in Machine Learning, Domain Adaptation and Few-Shot Learning
- 关键词：Lossy compression, Computer science, Speedup, Overhead (engineering), Convolutional neural network, Compression ratio, Bandwidth (computing), Process (computing), Computer engineering, Artificial neural network, Compression (physics), Bounded function, Data compression, Algorithm, Parallel computing, Artificial intelligence, Telecommunications
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep neural networks (DNNs) are becoming increasingly deeper, wider, and non-linear due to the growing demands on prediction accuracy and analysis quality. Training wide and deep neural networks require large amounts of storage resources such as memory because the intermediate activation data must be saved in the memory during forward propagation and then restored for backward propagation. However, state-of-the-art accelerators such as GPUs are only equipped with very limited memory capacities due to hardware design constraints, which significantly limits the maximum batch size and hence performance speedup when training large-scale DNNs. Traditional memory saving techniques either suffer from performance overhead or are constrained by limited interconnect bandwidth or specific interconnect technology. In this paper, we propose a novel memory-efficient CNN training framework (called COMET) that leverages error-bounded lossy compression to significantly reduce the memory requirement for training in order to allow training larger models or to accelerate training. Our framework purposely adopts error-bounded lossy compression with a strict error-controlling mechanism. Specifically, we perform a theoretical analysis on the compression error propagation from the altered activation data to the gradients, and empirically investigate the impact of altered gradients over the training process. Based on these analyses, we optimize the error-bounded lossy compression and propose an adaptive error-bound control scheme for activation data compression. Experiments demonstrate that our proposed framework can significantly reduce the training memory consumption by up to 13.5X over the baseline training and 1.8X over another state-of-the-art compression-based framework, respectively, with little or no accuracy loss.

## 16611. Learning Dual-Routing Capsule Graph Neural Network for Few-Shot Video Classification

- 标题：Learning Dual-Routing Capsule Graph Neural Network for Few-Shot Video Classification
- 作者：Yangbo Feng, Junyu Gao, Changsheng Xu
- 年份：2022
- 出版日期：2022-03-07
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2022.3156938
- OpenAlex ID：https://openalex.org/W4226340378
- 落地页：https://doi.org/10.1109/tmm.2022.3156938
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Discriminative model, Artificial intelligence, Routing (electronic design automation), Artificial neural network, Feature extraction, Graph, Pattern recognition (psychology), Machine learning, Theoretical computer science, Computer network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Few-shot video classification (video FSL), which learns classifiers for novel concepts, has gained increasing attention in the last few years from only a few samples. The existing methods rarely consider the local-global relation for video feature learning, which would ultimately result in low discriminative ability. Recently, the capsule network (CapsNet) has shown considerable potential in local-global relation learning in the image analysis field. However, CapsNet cannot be directly applied in video FSL since it ignores the interaction between videos and has high computational complexity. In this paper, a dual-routing capsule graph neural network (DR-CapsGNN) is proposed to solve the above issues. The DR-CapsGNN leverages CapsNet and a graph neural network (GNN) to explore local-global relations and to preserve the detailed properties. Specifically, the CapsGNN is used to learn video relations and structural information to generate high-quality hierarchical capsules. Furthermore, a novel dual-routing mechanism is designed to filter low-discriminative capsules from a holistic perspective and achieves high efficiency, which consists of inter-video and intra-video routing. Extensive experimental results demonstrate that our proposed approach performs favorably compared to state-of-the-art methods on two popular benchmarks.

## 16612. Temporal Attention-Pyramid Pooling for Temporal Action Detection

- 标题：Temporal Attention-Pyramid Pooling for Temporal Action Detection
- 作者：Ming-Gang Gan, Yan Zhang
- 年份：2022
- 出版日期：2022-04-08
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2022.3166025
- OpenAlex ID：https://openalex.org/W4226380330
- 落地页：https://doi.org/10.1109/tmm.2022.3166025
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Multimodal Machine Learning Applications, Video Analysis and Summarization
- 关键词：Computer science, Pooling, Discriminative model, Pyramid (geometry), Artificial intelligence, Construct (python library), Action (physics), Feature (linguistics), Machine learning, Pattern recognition (psychology), Task (project management)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Temporal action detection is a challenging task in video understanding, which is usually divided into two stages: proposal generation and classification. Learning proposal features is a crucial step for both stages. However, most methods ignore temporal information of proposals and consider background and action frames in proposals equally, leading to poor proposal features. In this paper, we propose a novel Temporal Attention-Pyramid Pooling (TAPP) method to learn proposal features of arbitrary length action proposals. The TAPP method exploits the attention mechanism to focus on the discriminative part of proposals, suppressing background influence on proposal features. It constructs a temporal pyramid structure to convert arbitrary length proposal feature sequences to multiple fixed-length sequences while retaining the temporal information. In the TAPP method, we design a multi-scale temporal function and apply it to the temporal pyramid to generate final proposal features. Based on the TAPP method, we construct a temporal action proposal generation model and an action proposal classification model, and then we perform extensive experiments on two mainstream temporal action detection datasets for the temporal action proposal and temporal action detection tasks to verify our models. On the THUMOS’14 dataset, our models based on the TAPP significantly outperform the previous state-of-the-art methods for both tasks.

## 16613. Stealthy and Flexible Trojan in Deep Learning Framework

- 标题：Stealthy and Flexible Trojan in Deep Learning Framework
- 作者：Yajie Wang, Kongyang Chen, Yu‐an Tan, Shuxin Huang, Wencong Ma, Yuanzhang Li
- 年份：2022
- 出版日期：2022-04-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Dependable and Secure Computing
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：1545-5971
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tdsc.2022.3164073
- OpenAlex ID：https://openalex.org/W4226394973
- 落地页：https://doi.org/10.1109/tdsc.2022.3164073
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Anomaly Detection Techniques and Applications
- 关键词：Backdoor, Trojan, Computer science, Computer security, Adversary, Flexibility (engineering), Deep learning, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep neural networks (DNNs) are increasingly used as the critical component of applications, bringing high computational costs. Many practitioners host their models on third-party platforms. This practice exposes DNNs to risks: A third party hosting the model may use a malicious deep learning framework to implement a backdoor attack. Our goal is to develop the realistic potential for backdoor attacks in third-party hosting platforms. We introduce a threatening and realistically implementable backdoor attack that is highly stealthy and flexible. We inject trojans by hijacking the built-in functions of the deep learning framework. Existing backdoor attacks rely on poisoning; its trigger is a special pattern superimposed on the input. Unlike existing backdoor attacks, the proposed sequential trigger is a specific sequence of clean image sets. Moreover, our attack is model agnostic and does not require retraining the model or modifying the parameters. Its stealthy is that injecting trojans will not change the model’s prediction for a clean image, so existing backdoor defenses cannot detect it. Its flexibility lies in that adversary can remodify the trojan behavior at any time. Extensive experiments on multiple benchmarks with different frameworks demonstrate that our attack achieves a perfect success rate (up to 100%) with minimal damage to model performance. And we can inject multiple trojans which do not affect each other at the same time, trojans hidden in the framework make a universal backdoor attack possible. Analysis and experiments further show that state-of-the-art defenses are ineffective against our attacks. Our work suggests that backdoor attacks in the supply chain need to be urgently explored.

## 16614. Data mining tools

- 标题：Data mining tools
- 作者：Andreas Bartschat, Markus Reischl, Ralf Mikut
- 年份：2019
- 出版日期：2019-02-22
- 类型：article
- 语言：en
- 来源：Wiley Interdisciplinary Reviews Data Mining and Knowledge Discovery
- 来源类型：journal
- 出版方：Wiley
- ISSN-L：1942-4787
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1002/widm.1309
- OpenAlex ID：https://openalex.org/W4243671181
- 落地页：https://doi.org/10.1002/widm.1309
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Data Stream Mining Techniques, Scientific Computing and Data Management
- 关键词：Variety (cybernetics), Computer science, Data science, Categorization, License, Data mining, Software, Big data, Visualization, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The development and application of data mining algorithms requires the use of powerful software tools. With challenges such as big data encountered in economy or gene sequencing for life science, data mining is important for daily problems as well as specialized fields. However, the large variety of requirements and user groups lead to a huge number and diversity of software tools. We give an overview by discussing the historical development and presenting a range of existing state‐of‐the‐art data mining and related tools. This paper is an update of our previous article from 2011 following the encyclopedic aspect of Wiley Interdisciplinary Reviews to include new findings or references and changing outdated information. However, since the paper should be able to stand alone, it includes many still valid elements of the previous article. Following the original paper, we propose criteria for the tool categorization based on different user groups, data structures, data mining tasks and methods, visualization and interaction styles, import and export options for data and models, platforms, and license policies. These criteria are then used to classify data mining tools into nine different categories. The typical characteristics of these types are explained and a selection of the most important tools is categorized. This article is categorized under: Application Areas &gt; Data Mining Software Tools

## 16615. RoughPSO: rough set-based particle swarm optimisation

- 标题：RoughPSO: rough set-based particle swarm optimisation
- 作者：Jian Cong Fan, Yang Li, Lei Yu Tang, Geng Kun Wu
- 年份：2018
- 出版日期：2018-01-01
- 类型：article
- 语言：en
- 来源：International Journal of Bio-Inspired Computation
- 来源类型：journal
- 出版方：Inderscience Publishers
- ISSN-L：1758-0366
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1504/ijbic.2018.096480
- OpenAlex ID：https://openalex.org/W4246876218
- 落地页：https://doi.org/10.1504/ijbic.2018.096480
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Machine Learning and Data Classification, Fuzzy Logic and Control Systems
- 关键词：Particle swarm optimization, Rough set, Mathematical optimization, Convergence (economics), Set (abstract data type), Position (finance), Computation, Evolutionary computation, Mathematics, Local optimum, Genetic algorithm, Algorithm, Computer science, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Particle swarm optimisation (PSO) is an optimisation algorithm based on stochastic search technique. PSO has many similar characteristics with evolutionary computation such as genetic algorithms (GA). Unlike GA, PSO has no evolution operators. In PSO, the particles (potential solutions) fly through the solution space by following the current optimum particles. However, PSO is easy to converge to a local optimum because the search process is stochastic. Rough set, in computer science, is a formal approximation of a conventional set in terms of a pair of sets. Rough set gives the lower and the upper approximation of the original set and is always used to deal with those uncertainty problems. In this paper, the properties of rough set theory are used to improve the local convergence problems in PSO, thereby an algorithm RoughPSO is proposed. RoughPSO utilises the lower- and upper-approximation sets of rough set to obtain the membership values. These values are then used to update the velocity and position of each particle. RoughPSO is applied for function optimisation and classification in machine learning. Empirical study shows that RoughPSO not only can solve the convergence to a local optimum, but also obtains higher classification accuracy rates on some datasets than those PSO-based classification algorithms.

## 16616. A framework for assessing AI ethics with applications to cybersecurity

- 标题：A framework for assessing AI ethics with applications to cybersecurity
- 作者：Danilo Bruschi, Nicla Diomede
- 年份：2022
- 出版日期：2022-05-18
- 类型：article
- 语言：en
- 来源：AI and Ethics
- 来源类型：journal
- 出版方：Springer Nature
- ISSN-L：2730-5953
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s43681-022-00162-8
- OpenAlex ID：https://openalex.org/W4280514508
- 落地页：https://doi.org/10.1007/s43681-022-00162-8
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s43681-022-00162-8.pdf
- 主主题：Ethics and Social Impacts of AI
- 主题：Ethics and Social Impacts of AI, Adversarial Robustness in Machine Learning, Neuroethics, Human Enhancement, Biomedical Innovations
- 关键词：Software deployment, Context (archaeology), Engineering ethics, Computer science, Knowledge management, Risk analysis (engineering), Management science, Business, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract In the last few years many scholars, public and private organizations have been involved in the definition of guidelines and frameworks for individuating the principles to adopt in the development and deployment of AI systems. Some authors, however, noted that the effectiveness of these guidelines or ethical codes on the developer’s community is very marginal. One of the obstacles that opposes to the effective implementation of ethical principles is the lack of an approach for solving tensions which arise when principles are applied. A possible solution to such an issue could be the adoption of a risk-based approach which is also advocated by many sources. To our knowledge, no concrete proposals have been presented in literature on how to perform a risk-based ethical assessment. In this paper we contribute to close this gap by introducing a framework based on a qualitative risk analysis approach for assessing the ethical impact underneath the introduction of an innovation either technological or organizational in a system. We will also show how the framework can be used for individuating suitable safeguards to adopt for balancing potential ethical infringements that the innovation may entail once implemented. Some case studies in the cybersecurity context are also described for showing the effectiveness of our approach.

## 16617. A multi-embedding neural model for incident video retrieval

- 标题：A multi-embedding neural model for incident video retrieval
- 作者：Ting-Hui Chiang, Yi‐Chun Tseng, Yu‐Chee Tseng
- 年份：2022
- 出版日期：2022-05-24
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2022.108807
- OpenAlex ID：https://openalex.org/W4281385024
- 落地页：https://doi.org/10.1016/j.patcog.2022.108807
- 主主题：Video Analysis and Summarization
- 主题：Video Analysis and Summarization, Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques
- 关键词：Computer science, Embedding, ENCODE, Video retrieval, Semantics (computer science), Similarity (geometry), Encoder, Artificial intelligence, Video tracking, Information retrieval, Pattern recognition (psychology), Video processing, Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16618. AS2T: Arbitrary Source-To-Target Adversarial Attack on Speaker Recognition Systems

- 标题：AS2T: Arbitrary Source-To-Target Adversarial Attack on Speaker Recognition Systems
- 作者：Guangke Chen, Zhe Zhao, Fu Song, Sen Chen, Lingling Fan, Yang Liu
- 年份：2022
- 出版日期：2022-07-08
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Dependable and Secure Computing
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：1545-5971
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tdsc.2022.3189397
- OpenAlex ID：https://openalex.org/W4281951480
- 落地页：https://doi.org/10.1109/tdsc.2022.3189397
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Geophysical Methods and Applications, Anomaly Detection Techniques and Applications
- 关键词：Adversarial system, Computer science, Transferability, Robustness (evolution), Leverage (statistics), Adversary, Computer security, Speech recognition, Machine learning, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Recent work has illuminated the vulnerability of speaker recognition systems (SRSs) against adversarial attacks, raising significant security concerns in deploying SRSs. However, they considered only a few settings (e.g., some combinations of source and target speakers), leaving many interesting and important settings in real-world attack scenarios alone. In this work, we present <sc xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">AS2T</small> , the first attack in this domain which covers all the settings, thus allows the adversary to craft adversarial voices using arbitrary source and target speakers for any of three main recognition tasks. Since none of the existing loss functions can be applied to all the settings, we explore many candidate loss functions for each setting including the existing and newly designed ones. We thoroughly evaluate their efficacy and find that some existing loss functions are suboptimal. Then, to improve the robustness of <sc xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">AS2T</small> towards practical over-the-air attack, we study the possible distortions occurred in over-the-air transmission, utilize different transformation functions with different parameters to model those distortions, and incorporate them into the generation of adversarial voices. Our simulated over-the-air evaluation validates the effectiveness of our solution in producing robust adversarial voices which remain effective under various hardware devices and various acoustic environments with different reverberation, ambient noises, and noise levels. Finally, we leverage <sc xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">AS2T</small> to perform thus far the largest-scale evaluation to understand transferability among 14 diverse SRSs. The transferability analysis provides many interesting and useful insights which challenge several findings and conclusion drawn in previous works in the image domain. Our study also sheds light on future directions of adversarial attacks in the speaker recognition domain.

## 16619. Minimum Noticeable Difference-Based Adversarial Privacy Preserving Image Generation

- 标题：Minimum Noticeable Difference-Based Adversarial Privacy Preserving Image Generation
- 作者：Wen Sun, Jian Jin, Weisi Lin
- 年份：2022
- 出版日期：2022-09-26
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2022.3210010
- OpenAlex ID：https://openalex.org/W4283204466
- 落地页：https://doi.org/10.1109/tcsvt.2022.3210010
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Generative Adversarial Networks and Image Synthesis, Advanced Neural Network Applications
- 关键词：Adversarial system, Computer science, Artificial intelligence, Deep learning, Perception, Image quality, Image (mathematics), Quality (philosophy), Machine learning, Computer vision, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep learning models are found to be vulnerable to adversarial examples, as wrong predictions can be caused by small perturbation in input for deep learning models. Most of the existing works of adversarial image generation try to achieve attacks for most models, while few of them make efforts on guaranteeing the perceptual quality of the adversarial examples. High quality adversarial examples matter for many applications, especially for the privacy preserving. In this work, we develop a framework based on the Minimum Noticeable Difference (MND) concept to generate adversarial privacy preserving images that have minimum perceptual difference from the clean ones but are able to attack deep learning models. To achieve this, an adversarial loss is firstly proposed to make the deep learning models attacked by the adversarial images successfully. Then, a perceptual quality-preserving loss is developed by taking the magnitude of perturbation and perturbation-caused structural and gradient changes into account, which aims to preserve high perceptual quality for adversarial image generation. To the best of our knowledge, this is the first work on exploring quality-preserving adversarial image generation based on the MND concept for privacy preserving. To evaluate its performance in terms of perceptual quality, the deep models on image classification and face recognition are tested with the proposed method and several anchor methods in this work. Extensive experimental results demonstrate that the proposed MND framework is capable of generating adversarial images with remarkably improved performance metrics (e.g., PSNR, SSIM, and MOS) than that generated with the anchor methods.

## 16620. Physical Adversarial Attack on a Robotic Arm

- 标题：Physical Adversarial Attack on a Robotic Arm
- 作者：Yifan Jia, Christopher M. Poskitt, Jun Sun, Sudipta Chattopadhyay
- 年份：2022
- 出版日期：2022-07-11
- 类型：article
- 语言：en
- 来源：IEEE Robotics and Automation Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2377-3766
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/lra.2022.3189783
- OpenAlex ID：https://openalex.org/W4285017746
- 落地页：https://doi.org/10.1109/lra.2022.3189783
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Bacillus and Francisella bacterial research
- 关键词：Adversarial system, Computer science, Artificial intelligence, Object (grammar), Context (archaeology), Robot, Deep learning, Artificial neural network, Computer security, Clipping (morphology), Robotic arm, Computer vision, Human–computer interaction
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Collaborative Robots (cobots) are regarded as highly safety-critical cyber-physical systems (CPSs) owing to their close physical interactions with humans. In settings such as smart factories, they are frequently augmented with AI. For example, in order to move materials, cobots utilize object detectors based on deep learning models. Deep learning, however, has been demonstrated as vulnerable to adversarial attacks: a minor change (noise) to benign input can fool the underlying neural networks and lead to a different result. While existing works have explored such attacks in the context of picture/object classification, less attention has been given to attacking neural networks used for identifying object locations, and demonstrating that this can actually lead to a physical attack in a real CPS. In this paper, we propose a method to generate adversarial patches for the object detectors of CPSs, in order to miscalibrate them and cause potentially dangerous physical effects. In particular, we evaluate our method on an industrial robotic arm for card gripping, demonstrating that it can be misled into clipping the operator’s hand instead of the card. To our knowledge, this is the first work to attack object locations and lead to an incident on human users by an actual system.

## 16621. Unsupervised Domain Adaptation Semantic Segmentation for Remote-Sensing Images via Covariance Attention

- 标题：Unsupervised Domain Adaptation Semantic Segmentation for Remote-Sensing Images via Covariance Attention
- 作者：Yikun Liu, Xudong Kang, Yuwen Huang, Kuikui Wang, Gongping Yang
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：en
- 来源：IEEE Geoscience and Remote Sensing Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1545-598X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/lgrs.2022.3189044
- OpenAlex ID：https://openalex.org/W4285154746
- 落地页：https://doi.org/10.1109/lgrs.2022.3189044
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Advanced Neural Network Applications, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Segmentation, Pattern recognition (psychology), Feature (linguistics), Weighting, Covariance, Test data, Metric (unit), Feature extraction, Image segmentation, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Semantic segmentation for remote sensing is a crucial but challenging task. Many supervised semantic segmentation methods rely heavily on a large-scale pixel-wise annotated data set, but it is time-consuming and laborious to provide manual annotation. However, due to the common domain shift of remote sensing images, a direct transfer might not perform well. Therefore, many unsupervised domain adaptation methods have been proposed to solve the data distribution discrepancy in remote-sensing data sets, but these methods cannot completely utilize the features extracted in the training process. In addition, the correlations between feature map channels are crucial for the pixel-wise classification task. In this letter, a covariance-based channel attention module is proposed to capture correlations by covariance metric and weighting the feature map channels. To further improve the domain adaptation performance, we propose a three-stage unsupervised domain adaptation semantic segmentation method for remote-sensing images, we fine-tune the model which has been trained on the source domain on the target domain via self training and knowledge distillation. To test the effectiveness of the proposed method, experiments are conducted on the ISPRS 2-D Semantic Labeling data set and an urban drone data set. Our method shows a better performance advantage compared with other state-of-the-art methods.

## 16622. DATA PREPROCESSING FOR MACHINE LEARNING

- 标题：DATA PREPROCESSING FOR MACHINE LEARNING
- 作者：A.A. Akimov, D.R. Valitov, A.I. Kubryak
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：ru
- 来源：Научное обозрение Технические науки (Scientific Review Technical Sciences)
- 来源类型：journal
- ISSN-L：2500-0799
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.17513/srts.1391
- OpenAlex ID：https://openalex.org/W4285276802
- 落地页：https://doi.org/10.17513/srts.1391
- 开放 PDF 链接：https://s.science-engineering.ru/pdf/2022/2/1391.pdf
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Artificial Intelligence in Healthcare, Data Mining Algorithms and Applications
- 关键词：Computer science, Preprocessor, Artificial intelligence, Machine learning, Data pre-processing
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
- , . , , .

## 16623. Embodied Active Domain Adaptation for Semantic Segmentation via Informative Path Planning

- 标题：Embodied Active Domain Adaptation for Semantic Segmentation via Informative Path Planning
- 作者：René Zurbrügg, Hermann Blum, César Cadena, Roland Siegwart, Lukas Schmid
- 年份：2022
- 出版日期：2022-07-15
- 类型：article
- 语言：en
- 来源：IEEE Robotics and Automation Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2377-3766
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/lra.2022.3188901
- OpenAlex ID：https://openalex.org/W4285507550
- 落地页：https://doi.org/10.1109/lra.2022.3188901
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Adaptation (eye), Embodied cognition, Segmentation, Domain adaptation, Path (computing), Domain (mathematical analysis), Artificial intelligence, Machine learning, Motion planning, Human–computer interaction, Robot, Labeled data
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This work presents an embodied agent that can adapt its semantic segmentation network to new indoor environments in a fully autonomous way. Because semantic segmentation networks fail to generalize well to unseen environments, the agent collects images of the new environment which are then used for self-supervised domain adaptation. We formulate this as an informative path planning problem, and present a novel information gain that leverages uncertainty extracted from the semantic model to safely collect relevant data. As domain adaptation progresses, these uncertainties change over time and the rapid learning feedback of our system drives the agent to collect different data. Experiments show that our method adapts to new environments faster and with higher final performance compared to an exploration objective, and can successfully be deployed to real-world environments on physical robots.

## 16624. Semisupervised Deep Learning for Image Classification With Distribution Mismatch: A Survey

- 标题：Semisupervised Deep Learning for Image Classification With Distribution Mismatch: A Survey
- 作者：Saul Calderon-Ramirez, Shengxiang Yang, David Elizondo
- 年份：2022
- 出版日期：2022-08-04
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Artificial Intelligence
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2691-4581
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tai.2022.3196326
- OpenAlex ID：https://openalex.org/W4289792623
- 落地页：https://doi.org/10.1109/tai.2022.3196326
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Machine Learning and Data Classification, Advanced Neural Network Applications
- 关键词：Overfitting, Artificial intelligence, Deep learning, Machine learning, Computer science, Generalization, Quality (philosophy), Pattern recognition (psychology), Artificial neural network, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep learning methodologies have been employed in several different fields, with an outstanding success in image recognition applications, such as material quality control, medical imaging, autonomous driving, etc. Deep learning models rely on the abundance of labeled observations to train a prospective model. These models are composed of millions of parameters to estimate, increasing the need of more training observations. Frequently, it is expensive to gather labeled observations of data, making the usage of deep learning models not ideal, as the model might overfit data. In a semisupervised setting, unlabeled data are used to improve the levels of accuracy and generalization of a model with small labeled datasets. Nevertheless, in many situations different unlabeled data sources might be available. This raises the risk of a significant distribution mismatch between the labeled and unlabeled datasets. Such phenomena can cause a considerable performance hit to typical semisupervised deep learning (SSDL) frameworks, which often assume that both labeled and unlabeled datasets are drawn from similar distributions. Therefore, in this article we study the latest approaches for SSDL for image recognition. Emphasis is made in SSDL models designed to deal with a distribution mismatch between the labeled and unlabeled datasets. We address open challenges with the aim to encourage the community to tackle them, and overcome the high data demand of traditional deep learning pipelines under real-world usage settings.

## 16625. Stream-based active learning with linear models

- 标题：Stream-based active learning with linear models
- 作者：Davide Cacciarelli, Murat Külahçı, John Tyssedal
- 年份：2022
- 出版日期：2022-08-13
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.knosys.2022.109664
- OpenAlex ID：https://openalex.org/W4291222583
- 落地页：https://doi.org/10.1016/j.knosys.2022.109664
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Fault Detection and Control Systems, Machine Learning and Data Classification
- 关键词：Computer science, Process (computing), Annotation, Data mining, Focus (optics), Machine learning, Quality (philosophy), Data stream, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The proliferation of automated data collection schemes and the advances in sensorics are increasing the amount of data we are able to monitor in real-time. However, given the high annotation costs and the time required by quality inspections, data is often available in an unlabeled form. This is fostering the use of active learning for the development of soft sensors and predictive models. In production, instead of performing random inspections to obtain product information, labels are collected by evaluating the information content of the unlabeled data. Several query strategy frameworks for regression have been proposed in the literature but most of the focus has been dedicated to the static pool-based scenario. In this work, we propose a new strategy for the stream-based scenario, where instances are sequentially offered to the learner, which must instantaneously decide whether to perform the quality check to obtain the label or discard the instance. The approach is inspired by the optimal experimental design theory and the iterative aspect of the decision-making process is tackled by setting a threshold on the informativeness of the unlabeled data points. The proposed approach is evaluated using numerical simulations and the Tennessee Eastman Process simulator. The results confirm that selecting the examples suggested by the proposed algorithm allows for a faster reduction in the prediction error.

## 16626. A Universal Defense Strategy for Data-Driven Power System Stability Assessment Models Under Adversarial Examples

- 标题：A Universal Defense Strategy for Data-Driven Power System Stability Assessment Models Under Adversarial Examples
- 作者：Chao Ren, Yan Xu
- 年份：2022
- 出版日期：2022-08-29
- 类型：article
- 语言：en
- 来源：IEEE Internet of Things Journal
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2327-4662
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/jiot.2022.3202267
- OpenAlex ID：https://openalex.org/W4293731772
- 落地页：https://doi.org/10.1109/jiot.2022.3202267
- 主主题：Smart Grid Security and Resilience
- 主题：Smart Grid Security and Resilience, Adversarial Robustness in Machine Learning, Network Security and Intrusion Detection
- 关键词：Adversarial system, Computer science, Smoothing, Robustness (evolution), Stability (learning theory), Artificial intelligence, Mathematical optimization, Binary number, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Based on machine learning (ML) technique, the datadriven power system stability assessment (SA) has received significant research interests in recent years. However, even with a high SA accuracy performance, the data-driven SA models may be vulnerable to adversarial examples (caused by some physical noises or adversarial attacks), which are very close to the original input but can result in a wrong SA result. To solve such threat, this paper firstly proposes a universal defense strategy for the MLbased SA models based on randomized smoothing algorithm to resist the adversarial attacks. Secondly, this paper proposes an effectiveness index for the proposed universal strategy to quantify the maximum ability of resistance to adversarial examples. Moreover, this paper provides the tight mathematical proof for the effectiveness index under the hard smoothing, soft smoothing, and binary scenarios. Simulation results verify that the proposed defense strategy can effectively resist the adversarial examples and the proposed effectiveness index can provide formal robustness guarantee for real-time power system SA applications.

## 16627. IterDANet: Iterative Intra-Domain Adaptation for Semantic Segmentation of Remote Sensing Images

- 标题：IterDANet: Iterative Intra-Domain Adaptation for Semantic Segmentation of Remote Sensing Images
- 作者：Yuxiang Cai, Yingchun Yang, Yongheng Shang, Zhenqian Chen, Zhengwei Shen, Jianwei Yin
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Geoscience and Remote Sensing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0196-2892
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tgrs.2022.3203040
- OpenAlex ID：https://openalex.org/W4293812316
- 落地页：https://doi.org/10.1109/tgrs.2022.3203040
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Remote-Sensing Image Classification
- 关键词：Computer science, Classifier (UML), Artificial intelligence, Segmentation, Domain adaptation, Entropy (arrow of time), Pattern recognition (psychology), Benchmark (surveying), Domain (mathematical analysis), Iterative method, Image segmentation, Computer vision, Data mining, Machine learning, Algorithm, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
When segmenting the continuous proliferation of unlabeled remotely sensed images, unsupervised domain adaptation (UDA) has become one of the most critical techniques and achieved significant performance. But in fact, there still exists a large performance gap between the existing UDA frameworks and supervised learning methods, for the majority of UDA frameworks don’t consider the intra-domain gap in the target domain. In this paper, to further minimize the complex intra-domain shift within the target domain in remote sensing, we propose a novel iterative intra-domain adaptation framework (IterDANet), which conducts inter-domain adaptation (InterDA), entropy-based ranking (ER) and iterative intra-domain adaptation (IntraDA). Specifically, first, to enhance the performance of InterDA built upon GAN-based image-to-image translation, we propose a new generator selection strategy to assess and choose a well-trained generator for the inter-domain classifier. Then, to produce more accurate pseudo labels for IntraDA, we propose a new pseudo label generation strategy to remove both high-entropy and low-confident pixels in predicted maps of inter-domain classifier. Finally, to better reduce the intra-domain gap, we propose to cluster all the target images into multiple subdomains using ER and iteratively align the cleanest subdomain with other noisy subdomains. The extensive experiments on the benchmark dataset, which includes cross-city aerial images, highlight the superiority and effectiveness of our IterDANet against the state-of-the-art UDA frameworks.

## 16628. MsVRL: Self-Supervised Multiscale Visual Representation Learning via Cross-Level Consistency for Medical Image Segmentation

- 标题：MsVRL: Self-Supervised Multiscale Visual Representation Learning via Cross-Level Consistency for Medical Image Segmentation
- 作者：Ruifeng Zheng, Ying Ying Zhong, Senxiang Yan, Hongcheng Sun, Haibin Shen, Kejie Huang
- 年份：2022
- 出版日期：2022-09-05
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Medical Imaging
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0278-0062
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmi.2022.3204551
- OpenAlex ID：https://openalex.org/W4294691359
- 落地页：https://doi.org/10.1109/tmi.2022.3204551
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Advanced Neural Network Applications
- 关键词：Segmentation, Computer science, Artificial intelligence, Representation (politics), Image segmentation, Feature learning, Pattern recognition (psychology), Matching (statistics), Embedding, Machine learning, Medical diagnosis, Scale-space segmentation, Consistency (knowledge bases), Segmentation-based object categorization, Computer vision, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Automated medical image segmentation for organs or lesions plays an essential role in clinical diagnoses and treatment plannings. However, training an accurate and robust segmentation model is still a long-standing challenge due to the time-consuming and expertise-intensive annotations for training data, especially 3-D medical images. Recently, self-supervised learning emerges as a promising approach for unsupervised visual representation learning, showing great potential to alleviate the expertise annotations for medical images. Although global representation learning has attained remarkable results on iconic datasets, such as ImageNet, it can not be applied directly to medical image segmentation, because the segmentation task is non-iconic, and the targets always vary in physical scales. To address these problems, we propose a Multi-scale Visual Representation self-supervised Learning (MsVRL) model, to perform finer-grained representation and deal with different target scales. Specifically, a multi-scale representation conception, a canvas matching method, an embedding pre-sampling module, a center-ness branch, and a cross-level consistent loss are introduced to improve the performance. After pre-trained on unlabeled datasets (RibFrac and part of MSD), MsVRL performs downstream segmentation tasks on labeled datasets (BCV, spleen of MSD, and KiTS). Results of the experiments show that MsVRL outperforms other state-of-the-art works on these medical image segmentation tasks.

## 16629. Stealthy attacks and attack-resilient interval observers

- 标题：Stealthy attacks and attack-resilient interval observers
- 作者：Kwassi H. Degue, Jérôme Le Ny, Denis Efimov
- 年份：2022
- 出版日期：2022-09-06
- 类型：article
- 语言：en
- 来源：Automatica
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0005-1098
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.automatica.2022.110558
- OpenAlex ID：https://openalex.org/W4294816500
- 落地页：https://doi.org/10.1016/j.automatica.2022.110558
- 主主题：Smart Grid Security and Resilience
- 主题：Smart Grid Security and Resilience, Fault Detection and Control Systems, Adversarial Robustness in Machine Learning
- 关键词：Observer (physics), Interval (graph theory), Bounded function, Control theory (sociology), Computer science, Actuator, Linear system, Interval arithmetic, Linear programming, State (computer science), Control (management), Mathematics, Algorithm, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16630. URPI-GRU: An approach of next POI recommendation based on user relationship and preference information

- 标题：URPI-GRU: An approach of next POI recommendation based on user relationship and preference information
- 作者：Jinfeng Fang, Xiangfu Meng
- 年份：2022
- 出版日期：2022-09-05
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2022.109848
- OpenAlex ID：https://openalex.org/W4294879413
- 落地页：https://doi.org/10.1016/j.knosys.2022.109848
- 主主题：Recommender Systems and Techniques
- 主题：Recommender Systems and Techniques, Advanced Graph Neural Networks, Multimodal Machine Learning Applications
- 关键词：Preference, Computer science, Term (time), Information retrieval, Construct (python library), Preference learning, User modeling, Data mining, Human–computer interaction, Artificial intelligence, User interface, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16631. SAR-PeGA: A Generation Method of Adversarial Examples for SAR Image Target Recognition Network

- 标题：SAR-PeGA: A Generation Method of Adversarial Examples for SAR Image Target Recognition Network
- 作者：Weijie Xia, Zhe Liu, Yi Li
- 年份：2022
- 出版日期：2022-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Aerospace and Electronic Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9251
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/taes.2022.3206261
- OpenAlex ID：https://openalex.org/W4295956293
- 落地页：https://doi.org/10.1109/taes.2022.3206261
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Bacillus and Francisella bacterial research, Advanced SAR Imaging Techniques
- 关键词：Synthetic aperture radar, Jamming, Computer science, Adversarial system, Artificial intelligence, Algorithm, Pattern recognition (psychology), Computer vision
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep learning (DL) is widely used in automatic target recognition (ATR) of synthetic aperture radar (SAR) images. Related researches show that DL models for SAR ATR are vulnerable to adversarial examples attack in the digital domain. However, how to generate adversarial examples in practical scenarios is critical and challenging. In this paper, we propose a systematic SAR perturbation generation algorithm (SAR-PeGA) for target recognition network. Firstly, assuming that some reflection phase tuning samples are located in the fixed area of SAR target, we adjust the phase characteristics of reflected signal with variable phase sequences. Secondly, we take the imperceptible perturbations from universal adversarial perturbations (UAP) as reference. Then, we construct the unconstrained minimum optimization model to find the specific phase sequences of tuning samples, and optimize the model with the adaptive moment estimation (Adam) optimizer. Finally, SAR adversarial examples can be flexibly generated through the proposed deceptive jamming model. Experimental results demonstrate that the proposed method can generate imperceptible jamming and effectively attack three classical recognition models.

## 16632. A Survey on the Use of Deep Learning Techniques for UAV Jamming and Deception

- 标题：A Survey on the Use of Deep Learning Techniques for UAV Jamming and Deception
- 作者：Ondřej Šimon, Tomáš Götthans
- 年份：2022
- 出版日期：2022-09-23
- 类型：article
- 语言：en
- 来源：Electronics
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2079-9292
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/electronics11193025
- OpenAlex ID：https://openalex.org/W4297192882
- 落地页：https://doi.org/10.3390/electronics11193025
- 开放 PDF 链接：https://www.mdpi.com/2079-9292/11/19/3025/pdf?version=1665481578
- 主主题：UAV Applications and Optimization
- 主题：UAV Applications and Optimization, Adversarial Robustness in Machine Learning, Wireless Communication Security Techniques
- 关键词：Deception, Drone, Popularity, Jamming, Computer science, Variety (cybernetics), Computer security, Deep learning, Artificial intelligence, Political science, Law
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Unmanned aerial vehicles (UAVs) can be used for a variety of illegal activities (e.g., industrial espionage, smuggling, terrorism). Given their growing popularity and availability, and advances in communications technology, more sophisticated ways to disable these vehicles must be sought. Various forms of jamming are used to disable drones, but more advanced techniques such as deception and UAV takeover are considerably difficult to implement, and there is a large research gap in this area. Currently, machine and deep learning techniques are popular and are also used in various drone-related applications. However, no detailed research has been conducted so far on the use of these techniques for jamming and deception of UAVs. This paper focuses on exploring the current techniques in the area of jamming and deception. A survey on the use of machine or deep learning specifically in UAV-related applications is also conducted. The paper provides insight into the issues described and encourages more detailed research in this area.

## 16633. Adversarial Sample Attack and Defense Method for Encrypted Traffic Data

- 标题：Adversarial Sample Attack and Defense Method for Encrypted Traffic Data
- 作者：Yi Ding, Guiqin Zhu, Dajiang Chen, Xue Qin, Mingsheng Cao, Zhiguang Qin
- 年份：2022
- 出版日期：2022-03-28
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Intelligent Transportation Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1524-9050
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tits.2022.3154884
- OpenAlex ID：https://openalex.org/W4297799123
- 落地页：https://doi.org/10.1109/tits.2022.3154884
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Internet Traffic Analysis and Secure E-voting
- 关键词：Adversarial system, Encryption, Sample (material), Computer science, Robustness (evolution), Artificial intelligence, Data mining, Computer security, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Resisting the adversarial sample attack on encrypted traffic is a challenging task in the Intelligent Transportation System. This paper focuses on the classification, adversarial samples attack and defense method for the encrypted traffic. To be more specific, the one-dimensional encrypted traffic data is firstly translated into the two-dimensional images for further utilization. Then different classification networks based on the deep learning algorithm are adopted to classify the encrypted traffic data. Moreover, various adversarial sample generation methods are employed to generate the adversarial sample to implement the attacking process on the classification network. Furthermore, the passive and active defense method are proposed to resist the adversarial sample attack: 1) the passive defense is used to denoise the perturbation in the adversarial sample and to restore to the original image; and 2) the active defense is used to resist the adversarial sample attack by leveraging the adversarial training method, which can improve the robustness of the classification network. We conduct the extensive experiments on the ISCXVPN2016 dataset to evaluate the effectiveness of classification, adversarial sample attacking and defending.

## 16634. A concealed poisoning attack to reduce deep neural networks’ robustness against adversarial samples

- 标题：A concealed poisoning attack to reduce deep neural networks’ robustness against adversarial samples
- 作者：Junhao Zheng, Patrick P. K. Chan, Huiyang Chi, Zhimin He
- 年份：2022
- 出版日期：2022-10-01
- 类型：article
- 语言：en
- 来源：Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0255
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ins.2022.09.060
- OpenAlex ID：https://openalex.org/W4298325779
- 落地页：https://doi.org/10.1016/j.ins.2022.09.060
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications
- 关键词：Adversarial system, Robustness (evolution), Computer science, Deep neural networks, Artificial intelligence, Artificial neural network, Computer security, Machine learning, Pattern recognition (psychology), Chemistry
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16635. Robustness of Deep Learning-Based Specific Emitter Identification under Adversarial Attacks

- 标题：Robustness of Deep Learning-Based Specific Emitter Identification under Adversarial Attacks
- 作者：Liting Sun, Da Ke, Xiang Wang, Zhitao Huang, Kaizhu Huang
- 年份：2022
- 出版日期：2022-10-07
- 类型：article
- 语言：en
- 来源：Remote Sensing
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2072-4292
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/rs14194996
- OpenAlex ID：https://openalex.org/W4303980686
- 落地页：https://doi.org/10.3390/rs14194996
- 开放 PDF 链接：https://www.mdpi.com/2072-4292/14/19/4996/pdf?version=1665483397
- 主主题：Wireless Signal Modulation Classification
- 主题：Wireless Signal Modulation Classification, Adversarial Robustness in Machine Learning, Integrated Circuits and Semiconductor Failure Analysis
- 关键词：Computer science, Adversarial system, Robustness (evolution), Artificial intelligence, Artificial neural network, Deep learning, Vulnerability (computing), Machine learning, Pattern recognition (psychology), Data mining, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep learning (DL)-based specific emitter identification (SEI) technique can automatically extract radio frequency (RF) fingerprint features in RF signals to distinguish between legal and illegal devices and enhance the security of wireless network. However, deep neural network (DNN) can easily be fooled by adversarial examples or perturbations of the input data. If a malicious device emits signals containing a specially designed adversarial samples, will the DL-based SEI still work stably to correctly identify the malicious device? To the best of our knowledge, this research is still blank, let alone the corresponding defense methods. Therefore, this paper designs two scenarios of attack and defense and proposes the corresponding implementation methods to specializes in the robustness of DL-based SEI under adversarial attacks. On this basis, detailed experiments are carried out based on the real-world data and simulation data. The attack scenario is that the malicious device adds an adversarial perturbation signal specially designed to the original signal, misleading the original system to make a misjudgment. Experiments based on three different attack generation methods show that DL-based SEI is very vulnerability. Even if the intensity is very low, without affecting the probability density distribution of the original signal, the performance can be reduced to about 50%, and at −22 dB it is completely invalid. In the defense scenario, the adversarial training (AT) of DL-based SEI is added, which can significantly improve the system’s performance under adversarial attacks, with ≥60% improvement in the recognition rate compared to the network without AT. Further, AT has a more robust effect on white noise. This study fills the relevant gaps and provides guidance for future research. In the future research, the impact of adversarial attacks must be considered, and it is necessary to add adversarial training in the training process.

## 16636. An Ensemble Framework to Improve the Accuracy of Prediction Using Clustered Random-Forest and Shrinkage Methods

- 标题：An Ensemble Framework to Improve the Accuracy of Prediction Using Clustered Random-Forest and Shrinkage Methods
- 作者：Zari Farhadi, Hossein Bevrani, Mohammad‐Reza Feizi‐Derakhshi, Wonjoon Kim, Muhammad Fazal Ijaz
- 年份：2022
- 出版日期：2022-10-20
- 类型：article
- 语言：en
- 来源：Applied Sciences
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2076-3417
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/app122010608
- OpenAlex ID：https://openalex.org/W4306920896
- 落地页：https://doi.org/10.3390/app122010608
- 开放 PDF 链接：https://www.mdpi.com/2076-3417/12/20/10608/pdf?version=1666605792
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Machine Learning and Data Classification, Imbalanced Data Classification Techniques
- 关键词：Random forest, Computer science, Cluster analysis, Variance (accounting), Ensemble learning, Tree (set theory), Data mining, Machine learning, Algorithm, Artificial intelligence, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Nowadays, in the topics related to prediction, in addition to increasing the accuracy of existing algorithms, the reduction of computational time is a challenging issue that has attracted much attention. Since the existing methods may not have enough efficiency and accuracy, we use a combination of machine-learning algorithms and statistical methods to solve this problem. Furthermore, we reduce the computational time in the testing model by automatically reducing the number of trees using penalized methods and ensembling the remaining trees. We call this efficient combinatorial method “ensemble of clustered and penalized random forest (ECAPRAF)”. This method consists of four fundamental parts. In the first part, k-means clustering is used to identify homogeneous subsets of data and assign them to similar groups. In the second part, a tree-based algorithm is used within each cluster as a predictor model; in this work, random forest is selected. In the next part, penalized methods are used to reduce the number of random-forest trees and remove high-variance trees from the proposed model. This increases model accuracy and decreases the computational time in the test phase. In the last part, the remaining trees within each cluster are combined. The results of the simulation and two real datasets based on the WRMSE criterion show that our proposed method has better performance than the traditional random forest by reducing approximately 12.75%, 11.82%, 12.93%, and 11.68% and selecting 99, 106, 113, and 118 trees for the ECAPRAF–EN algorithm.

## 16637. Intellectual property protection of DNN models

- 标题：Intellectual property protection of DNN models
- 作者：Sen Peng, Yufei Chen, Jie Xu, Zizhuo Chen, Cong Wang, Xiaohua Jia
- 年份：2022
- 出版日期：2022-11-22
- 类型：article
- 语言：en
- 来源：World Wide Web
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1386-145X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11280-022-01113-3
- OpenAlex ID：https://openalex.org/W4309699960
- 落地页：https://doi.org/10.1007/s11280-022-01113-3
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Digital Media Forensic Detection, Physical Unclonable Functions (PUFs) and Hardware Security
- 关键词：Computer science, Intellectual property, Artificial neural network, Deep neural networks, Artificial intelligence, Inference, Deep learning, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16638. Targeted Universal Adversarial Examples for Remote Sensing

- 标题：Targeted Universal Adversarial Examples for Remote Sensing
- 作者：Tao Bai, Hao Wang, Bihan Wen
- 年份：2022
- 出版日期：2022-11-17
- 类型：article
- 语言：en
- 来源：Remote Sensing
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2072-4292
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/rs14225833
- OpenAlex ID：https://openalex.org/W4309717800
- 落地页：https://doi.org/10.3390/rs14225833
- 开放 PDF 链接：https://www.mdpi.com/2072-4292/14/22/5833/pdf?version=1669044622
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Bacillus and Francisella bacterial research, Forensic and Genetic Research
- 关键词：Adversarial system, Computer science, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Researchers are focusing on the vulnerabilities of deep learning models for remote sensing; various attack methods have been proposed, including universal adversarial examples. Existing universal adversarial examples, however, are only designed to fool deep learning models rather than target specific goals, i.e., targeted attacks. To this end, we propose two variants of universal adversarial examples called targeted universal adversarial examples and source-targeted universal adversarial examples. Extensive experiments on three popular datasets showed strong attackability of the two targeted adversarial variants. We hope such strong attacks can inspire and motivate research on the defenses against adversarial examples in remote sensing.

## 16639. A multi-layer memory sharing network for video captioning

- 标题：A multi-layer memory sharing network for video captioning
- 作者：Tian-Zi Niu, Shan-Shan Dong, Zhen-Duo Chen, Xin Luo, Zi Huang, Shanqing Guo, Xin-Shun Xu
- 年份：2022
- 出版日期：2022-11-23
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2022.109202
- OpenAlex ID：https://openalex.org/W4309724203
- 落地页：https://doi.org/10.1016/j.patcog.2022.109202
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Construct (python library), Closed captioning, Layer (electronics), Code (set theory), Recurrent neural network, Decoding methods, Stack (abstract data type), Artificial intelligence, Image (mathematics), Algorithm, Computer network, Artificial neural network, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16640. Is image-to-image translation the panacea for multimodal image registration? A comparative study

- 标题：Is image-to-image translation the panacea for multimodal image registration? A comparative study
- 作者：Jiahao Lu, Johan Öfverstedt, Joakim Lindblad, Nataša Sladoje
- 年份：2022
- 出版日期：2022-11-28
- 类型：article
- 语言：en
- 来源：PLoS ONE
- 来源类型：journal
- 出版方：Public Library of Science
- ISSN-L：1932-6203
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1371/journal.pone.0276196
- OpenAlex ID：https://openalex.org/W4310092560
- 落地页：https://doi.org/10.1371/journal.pone.0276196
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Multimodal Machine Learning Applications, Vehicle License Plate Recognition
- 关键词：Translation (biology), Image registration, Panacea (medicine), Artificial intelligence, Image (mathematics), Computer science, Computer vision, Image translation, Medicine, Biology, Pathology, Genetics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Despite current advancement in the field of biomedical image processing, propelled by the deep learning revolution, multimodal image registration, due to its several challenges, is still often performed manually by specialists. The recent success of image-to-image (I2I) translation in computer vision applications and its growing use in biomedical areas provide a tempting possibility of transforming the multimodal registration problem into a, potentially easier, monomodal one. We conduct an empirical study of the applicability of modern I2I translation methods for the task of rigid registration of multimodal biomedical and medical 2D and 3D images. We compare the performance of four Generative Adversarial Network (GAN)-based I2I translation methods and one contrastive representation learning method, subsequently combined with two representative monomodal registration methods, to judge the effectiveness of modality translation for multimodal image registration. We evaluate these method combinations on four publicly available multimodal (2D and 3D) datasets and compare with the performance of registration achieved by several well-known approaches acting directly on multimodal image data. Our results suggest that, although I2I translation may be helpful when the modalities to register are clearly correlated, registration of modalities which express distinctly different properties of the sample are not well handled by the I2I translation approach. The evaluated representation learning method, which aims to find abstract image-like representations of the information shared between the modalities, manages better, and so does the Mutual Information maximisation approach, acting directly on the original multimodal images. We share our complete experimental setup as open-source (https://github.com/MIDA-group/MultiRegEval), including method implementations, evaluation code, and all datasets, for further reproducing and benchmarking.

## 16641. Exploring Optimal Reaction Conditions Guided by Graph Neural Networks and Bayesian Optimization

- 标题：Exploring Optimal Reaction Conditions Guided by Graph Neural Networks and Bayesian Optimization
- 作者：Youngchun Kwon, Dongseon Lee, Jin Woo Kim, Youn-Suk Choi, Sun Kim
- 年份：2022
- 出版日期：2022-12-02
- 类型：article
- 语言：en
- 来源：ACS Omega
- 来源类型：journal
- 出版方：American Chemical Society
- ISSN-L：2470-1343
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1021/acsomega.2c05165
- OpenAlex ID：https://openalex.org/W4311376455
- 落地页：https://doi.org/10.1021/acsomega.2c05165
- 主主题：Machine Learning in Materials Science
- 主题：Machine Learning in Materials Science, Machine Learning and Data Classification, Computational Drug Discovery Methods
- 关键词：Bayesian optimization, Computer science, Artificial neural network, Process (computing), Graph, Yield (engineering), Artificial intelligence, Machine learning, Bayesian network, Process optimization, Mathematical optimization, Mathematics, Engineering, Theoretical computer science, Materials science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The optimization of organic reaction conditions to obtain the target product in high yield is crucial to avoid expensive and time-consuming chemical experiments. Advancements in artificial intelligence have enabled various data-driven approaches to predict suitable chemical reaction conditions. However, for many novel syntheses, the process to determine good reaction conditions is inevitable. Bayesian optimization (BO), an iterative optimization algorithm, demonstrates exceptional performance to identify reagents compared to synthesis experts. However, BO requires several initial randomly selected experimental results (yields) to train a surrogate model (approximately 10 experimental trials). Parts of this process, such as the cold-start problem in recommender systems, are inefficient. Here, we present an efficient optimization algorithm to determine suitable conditions based on BO that is guided by a graph neural network (GNN) trained on a million organic synthesis experiment data. The proposed method determined 8.0 and 8.7% faster high-yield reaction conditions than state-of-the-art algorithms and 50 human experts, respectively. In 22 additional optimization tests, the proposed method needed 4.7 trials on average to find conditions higher than the yield of the conditions recommended by five synthesis experts. The proposed method is considered in a situation of having a reaction dataset for training GNN.

## 16642. Understanding How CNNs Recognize Facial Expressions: A Case Study with LIME and CEM

- 标题：Understanding How CNNs Recognize Facial Expressions: A Case Study with LIME and CEM
- 作者：Guillermo del Castillo Torres, Maria Francesca Roig-Maimó, Miquel Mascaró-Oliver, Esperança Amengual, Ramon Mas-Sansó
- 年份：2022
- 出版日期：2022-12-23
- 类型：article
- 语言：en
- 来源：Sensors
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1424-8220
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/s23010131
- OpenAlex ID：https://openalex.org/W4312171814
- 落地页：https://doi.org/10.3390/s23010131
- 开放 PDF 链接：https://www.mdpi.com/1424-8220/23/1/131/pdf?version=1671786914
- 主主题：Explainable Artificial Intelligence (XAI)
- 主题：Explainable Artificial Intelligence (XAI), Adversarial Robustness in Machine Learning, Machine Learning in Healthcare
- 关键词：Artificial intelligence, Convolutional neural network, Lime, Computer science, Pattern recognition (psychology), Facial expression, Process (computing), Contextual image classification, Machine learning, Expression (computer science), Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Recognizing facial expressions has been a persistent goal in the scientific community. Since the rise of artificial intelligence, convolutional neural networks (CNN) have become popular to recognize facial expressions, as images can be directly used as input. Current CNN models can achieve high recognition rates, but they give no clue about their reasoning process. Explainable artificial intelligence (XAI) has been developed as a means to help to interpret the results obtained by machine learning models. When dealing with images, one of the most-used XAI techniques is LIME. LIME highlights the areas of the image that contribute to a classification. As an alternative to LIME, the CEM method appeared, providing explanations in a way that is natural for human classification: besides highlighting what is sufficient to justify a classification, it also identifies what should be absent to maintain it and to distinguish it from another classification. This study presents the results of comparing LIME and CEM applied over complex images such as facial expression images. While CEM could be used to explain the results on images described with a reduced number of features, LIME would be the method of choice when dealing with images described with a huge number of features.

## 16643. CrossDet++: Growing Crossline Representation for Object Detection

- 标题：CrossDet++: Growing Crossline Representation for Object Detection
- 作者：Heqian Qiu, Hongliang Li, Qingbo Wu, Jianhua Cui, Zichen Song, Lanxiao Wang, Minjian Zhang
- 年份：2022
- 出版日期：2022-10-03
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2022.3211734
- OpenAlex ID：https://openalex.org/W4312313652
- 落地页：https://doi.org/10.1109/tcsvt.2022.3211734
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications
- 关键词：Object detection, Computer science, Object (grammar), Representation (politics), Artificial intelligence, Set (abstract data type), Noise (video), Pixel, Pattern recognition (psychology), Computer vision, Pascal (unit), Cognitive neuroscience of visual object recognition, Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In object detection, precise object representation is a key factor to successfully classify and locate objects of an image. Existing methods usually use rectangular anchor boxes or a set of points to represent objects. However, these methods either introduce background noise or miss the continuous appearance information inside the object, and thus cause incorrect detection results. In this paper, we propose a novel anchor-free object detection network, called CrossDet++, which uses a set of growing crosslines along horizontal and vertical axes as object representations. An object can be flexibly represented as crosslines in different combinations, which inspires us to select the expressive crossline to effectively reduce the interference of noise. Meanwhile, the crossline representation takes into account the continuous adjacent object information, which is useful to enhance the discriminability of object features and find the object boundaries. Based on the learned crosslines, we propose an axis-query crossline growing module to adaptively capture features of crosslines and query surrounding pixels related to the line features for subsequent growing of crosslines. Their growing offsets and scales can be supervised by a decoupled regression mechanism, which limits the regression target to a specific direction for decreasing the optimization difficulty. During the training, we design a semantic-guided label assignment to emphasize the importance of crossline targets with higher semantic richness, further improving the detection performance. The experiment results demonstrate the effectiveness of our proposed method. Code can be available at: <uri xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">https://github.com/QiuHeqian/CrossDet</uri> .

## 16644. Simple But Powerful, a Language-Supervised Method for Image Emotion Classification

- 标题：Simple But Powerful, a Language-Supervised Method for Image Emotion Classification
- 作者：Sinuo Deng, Lifang Wu, Ge Shi, Lehao Xing, Wenjin Hu, Heng Zhang, Ye Xiang
- 年份：2022
- 出版日期：2022-11-28
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Affective Computing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1949-3045
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/taffc.2022.3225049
- OpenAlex ID：https://openalex.org/W4313042449
- 落地页：https://doi.org/10.1109/taffc.2022.3225049
- 主主题：Sentiment Analysis and Opinion Mining
- 主题：Sentiment Analysis and Opinion Mining, Multimodal Machine Learning Applications, Text and Document Classification Technologies
- 关键词：Computer science, Task (project management), Emotion classification, Notation, Artificial intelligence, Image (mathematics), Simple (philosophy), Natural language processing, Margin (machine learning), Pattern recognition (psychology), Machine learning, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Image emotion classification is an important computer vision task to extract emotions from images. The methods for image emotion classification (IEC) are primarily based on label or distribution as a supervision signal, which neither has enough accessibility nor diversity, limiting the development of IEC research. Inspired by psychology research and the recent booming of large-scale pretrained language models. We figure out a language-supervised paradigm, which can cleverly combine the features of language and visual emotion to drive the visual model to gain stronger emotional discernment with language prompts. To practice the paradigm, we present a conceptually simple while empirically powerful framework for image emotion classification, SimEmotion. That we propose a prompt-based fine-tuning strategy to learn task-specific representations by composing a template with the emotion-level concept and entity-level information. Evaluations on four widely-used affective datasets, namely, Flickr and Instagram (FI), EmotionROI, Twitter I, and Twitter II, demonstrate that the proposed algorithm outperforms the state-of-the-art methods with a large margin (i.e., <inline-formula><tex-math notation="LaTeX">$8.42\%$</tex-math></inline-formula> absolute accuracy gain on EmotionROI) on image emotion classification tasks. Our codes will be publicly available for research purposes.

## 16645. Deep Cross-Layer Collaborative Learning Network for Online Knowledge Distillation

- 标题：Deep Cross-Layer Collaborative Learning Network for Online Knowledge Distillation
- 作者：Tongtong Su, Qiyu Liang, Jinsong Zhang, Zhaoyang Yu, Ziyue Xu, Gang Wang, Xiaoguang Liu
- 年份：2022
- 出版日期：2022-11-14
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2022.3222013
- OpenAlex ID：https://openalex.org/W4313159787
- 落地页：https://doi.org/10.1109/tcsvt.2022.3222013
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Advanced Neural Network Applications
- 关键词：Computer science, Feature (linguistics), Artificial intelligence, Layer (electronics), Feature learning, Process (computing), Collaborative learning, Machine learning, Representation (politics), Construct (python library), Deep learning, Matching (statistics), Knowledge management
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Recent online knowledge distillation (OKD) methods focus on capturing rich and useful intermediate information by performing multi-layer feature learning. Existing works only consider intermediate layer feature maps between the same layers and ignore valuable information across layers, which results in the lack of appropriate cross-layer supervision in detail and the process of learning. Besides, this manner provides insufficient supervision information to supervise the learning of student, since it fails to construct a qualified teacher. In this work, we propose a Deep Cross-layer Collaborative Learning network (DCCL) for OKD, which efficiently exploits fruitful knowledge of peer student models by keeping appropriate intermediate cross-layer supervision. Specifically, each student gradually integrates its own features at different layers for feature matching, so as to effectively utilize features in low and high levels for learning more composite knowledge. Moreover, we assign a collaborative knowledge learning strategy, in which a qualified teacher is established via fusing the features of last convolution layers for enhancing high-level representation. In this way, all student models continuously transfer the rich teacher’s internal representation as well as capture its dynamic growth process, and in turn assist the learning of the fusion teacher to further supervise students. In the experiments, our proposed DCCL has shown great generalization ability with various backbone models on CIFAR-100, Tiny ImageNet and ImageNet, and also demonstrated superior performance against mainstream OKD works. Our code is available here: <uri xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">https://github.com/nanxiaotong/DCCL</uri> .

## 16646. Graph neural networks for decentralized multi-agent perimeter defense

- 标题：Graph neural networks for decentralized multi-agent perimeter defense
- 作者：Elijah S. Lee, Lifeng Zhou, Alejandro Ribeiro, Vijay Kumar
- 年份：2023
- 出版日期：2023-01-13
- 类型：article
- 语言：en
- 来源：Frontiers in Control Engineering
- 来源类型：journal
- 出版方：Frontiers Media
- ISSN-L：2673-6268
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3389/fcteg.2023.1104745
- OpenAlex ID：https://openalex.org/W4315782509
- 落地页：https://doi.org/10.3389/fcteg.2023.1104745
- 开放 PDF 链接：https://www.frontiersin.org/articles/10.3389/fcteg.2023.1104745/pdf
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Reinforcement Learning in Robotics, Advanced Graph Neural Networks
- 关键词：Computer science, Scalability, Leverage (statistics), Artificial intelligence, Implementation, Artificial neural network, Graph, Machine learning, Perimeter, Distributed computing, Theoretical computer science, Software engineering, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this work, we study the problem of decentralized multi-agent perimeter defense that asks for computing actions for defenders with local perceptions and communications to maximize the capture of intruders. One major challenge for practical implementations is to make perimeter defense strategies scalable for large-scale problem instances. To this end, we leverage graph neural networks (GNNs) to develop an imitation learning framework that learns a mapping from defenders’ local perceptions and their communication graph to their actions. The proposed GNN-based learning network is trained by imitating a centralized expert algorithm such that the learned actions are close to that generated by the expert algorithm. We demonstrate that our proposed network performs closer to the expert algorithm and is superior to other baseline algorithms by capturing more intruders. Our GNN-based network is trained at a small scale and can be generalized to large-scale cases. We run perimeter defense games in scenarios with different team sizes and configurations to demonstrate the performance of the learned network.

## 16647. Multilevel Heterogeneous Domain Adaptation Method for Remote Sensing Image Segmentation

- 标题：Multilevel Heterogeneous Domain Adaptation Method for Remote Sensing Image Segmentation
- 作者：Chenbin Liang, Bo Cheng, Baihua Xiao, Yunyun Dong, Jinfen Chen
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Geoscience and Remote Sensing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0196-2892
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tgrs.2023.3236957
- OpenAlex ID：https://openalex.org/W4316661208
- 落地页：https://doi.org/10.1109/tgrs.2023.3236957
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Cancer-related molecular mechanisms research
- 关键词：Computer science, Segmentation, Domain (mathematical analysis), Consistency (knowledge bases), Field (mathematics), Domain adaptation, Feature (linguistics), Image segmentation, Artificial intelligence, Remote sensing, Adaptation (eye), Data mining, Pattern recognition (psychology), Geography
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Due to more abundant data sources, more various objects of interest, and more time-consuming annotations, there is a large amount of out-of-distribution (OOD) data in the remote sensing field, on which the performance of high-accuracy image segmentation models trained under ideal experimental conditions generally degrades dramatically. Domain adaptation (DA) consequently comes into being, which aims to learn the predictor for the label-scarce target domain of interest with the help of the label-sufficient source domain in the presence of the distribution difference, namely, domain shift, between the two domains. However, the off-the-shelf DA methods for image segmentation not only struggle to cope with the more complex domain shift problems in remote sensing imagery but also almost cannot process heterogeneous data directly without information loss. While the current heterogeneous DA methods mostly still rely on some supervision information from the target domain, which is typically inaccessible in the real world. To overcome these drawbacks, we propose the multilevel heterogeneous unsupervised DA (UDA) method, termed MHDA, which unifies the instance-level DA based on cycle consistency, the feature-level DA based on contrastive learning, and the decision-level DA based on task consistency into a framework to more effectively handle the complex domain shift and heterogeneous data. After that, extensive DA experiments are conducted on the International Society for Photogrammetry and Remote Sensing (ISPRS) dataset, the BigCity dataset constructed by ourselves, and the Wuhan University (WHU) dataset, to explore the effect of each module in MHDA, the necessity of heterogeneous DA, and the effectiveness of multilevel DA. And the results demonstrate that MHDA can achieve superior performance on the remote sensing image segmentation task, compared with several state-of-the-art DA methods.

## 16648. COMET: Coverage-guided Model Generation For Deep Learning Library Testing

- 标题：COMET: Coverage-guided Model Generation For Deep Learning Library Testing
- 作者：Meiziniu Li, Jialun Cao, Yongqiang Tian, Tsz On Li, Ming Wen, Shing-Chi Cheung
- 年份：2023
- 出版日期：2023-02-08
- 类型：article
- 语言：en
- 来源：ACM Transactions on Software Engineering and Methodology
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1049-331X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1145/3583566
- OpenAlex ID：https://openalex.org/W4319594569
- 落地页：https://doi.org/10.1145/3583566
- 主主题：Software Testing and Debugging Techniques
- 主题：Software Testing and Debugging Techniques, Adversarial Robustness in Machine Learning, Machine Learning and Data Classification
- 关键词：Comet, Computer science, Layer (electronics), Set (abstract data type), Test set, Artificial intelligence, Machine learning, Algorithm, Data mining, Programming language, Chemistry
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Recent deep learning (DL) applications are mostly built on top of DL libraries. The quality assurance of these libraries is critical to the dependable deployment of DL applications. Techniques have been proposed to generate various DL models and apply them to test these libraries. However, their test effectiveness is constrained by the diversity of layer API calls in their generated DL models. Our study reveals that these techniques can cover at most 34.1% layer inputs, 25.9% layer parameter values, and 15.6% layer sequences. As a result, we find that many bugs arising from specific layer API calls (i.e., specific layer inputs, parameter values, or layer sequences) can be missed by existing techniques. Because of this limitation, we propose COMET to effectively generate DL models with diverse layer API calls for DL library testing. COMET: (1) designs a set of mutation operators and a coverage-based search algorithm to diversify layer inputs, layer parameter values, and layer sequences in DL models. (2) proposes a model synthesis method to boost the test efficiency without compromising the layer API call diversity. Our evaluation result shows that COMET outperforms baselines by covering twice as many layer inputs (69.7% vs. 34.1%), layer parameter values (50.2% vs. 25.9%), and layer sequences (39.0% vs. 15.6%) as those by the state-of-the-art. Moreover, COMET covers 3.4% more library branches than those by existing techniques. Finally, COMET detects 32 new bugs in the latest version of eight popular DL libraries, including TensorFlow and MXNet, with 21 of them confirmed by DL library developers and seven of those confirmed bugs have been fixed by developers.

## 16649. Toward Effective Domain Adaptive Retrieval

- 标题：Toward Effective Domain Adaptive Retrieval
- 作者：Haixin Wang, Jinan Sun, Xiao Luo, Wei Xiang, Shikun Zhang, Chong Chen, Xian‐Sheng Hua
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2023.3242777
- OpenAlex ID：https://openalex.org/W4319878852
- 落地页：https://doi.org/10.1109/tip.2023.3242777
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications
- 关键词：Computer science, Hash function, Domain (mathematical analysis), Exploit, Image retrieval, Semantics (computer science), Information retrieval, Hamming space, Artificial intelligence, Centroid, Machine learning, Data mining, Theoretical computer science, Hamming code, Image (mathematics), Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This paper studies the problem of unsupervised domain adaptive hashing, which is less-explored but emerging for efficient image retrieval, particularly for cross-domain retrieval. This problem is typically tackled by learning hashing networks with pseudo-labeling and domain alignment techniques. Nevertheless, these approaches usually suffer from overconfident and biased pseudo-labels and inefficient domain alignment without sufficiently exploring semantics, thus failing to achieve satisfactory retrieval performance. To tackle this issue, we present PEACE, a principled framework which holistically explores semantic information in both source and target data and extensively incorporates it for effective domain alignment. For comprehensive semantic learning, PEACE leverages label embeddings to guide the optimization of hash codes for source data. More importantly, to mitigate the effects of noisy pseudo-labels, we propose a novel method to holistically measure the uncertainty of pseudo-labels for unlabeled target data and progressively minimize them through alternative optimization under the guidance of the domain discrepancy. Additionally, PEACE effectively removes domain discrepancy in the Hamming space from two views. In particular, it not only introduces composite adversarial learning to implicitly explore semantic information embedded in hash codes, but also aligns cluster semantic centroids across domains to explicitly exploit label information. Experimental results on several popular domain adaptive retrieval benchmarks demonstrate the superiority of our proposed PEACE compared with various state-of-the-art methods on both single-domain and cross-domain retrieval tasks. Our source codes are available at https://github.com/WillDreamer/PEACE.

## 16650. Unified Architecture Adaptation for Compressed Domain Semantic Inference

- 标题：Unified Architecture Adaptation for Compressed Domain Semantic Inference
- 作者：Zhihao Duan, Zhan Ma, Fengqing Zhu
- 年份：2023
- 出版日期：2023-01-30
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tcsvt.2023.3240391
- OpenAlex ID：https://openalex.org/W4320015860
- 落地页：https://doi.org/10.1109/tcsvt.2023.3240391
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, COVID-19 diagnosis using AI, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Inference, Lossy compression, Deep learning, Pixel, Domain (mathematical analysis), Computer vision, Image compression, Segmentation, Pattern recognition (psychology), Image (mathematics), Machine learning, Image processing, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Advances in both lossy image compression and semantic content understanding have been greatly fueled by deep learning techniques, yet these two tasks have been developed separately for the past decades. In this work, we address the problem of directly executing semantic inference from quantized latent features in the deep compressed domain without pixel reconstruction. Although different methods have been proposed for this problem setting, they either are restrictive to a specific architecture, or are sub-optimal in terms of compressed domain task accuracy. In contrast, we propose a lightweight, plug-and-play solution which is generally compliant with popular learned image coders and deep vision models, making it attractive to vast applications. Our method adapts prevalent pixel domain neural models that are deployed for various vision tasks to directly accept quantized latent features (other than pixels). We further suggest training the compressed domain model by transferring knowledge from its corresponding pixel domain counterpart. Experiments show that our method is compliant with popular learned image coders and vision task models. Under fair comparison, our approach outperforms a baseline method by a) more than 3% top-1 accuracy for compressed domain classification, and b) more than 7% mIoU for compressed domain semantic segmentation, at various data rates.

## 16651. Probabilistic Attention Based on Gaussian Processes for Deep Multiple Instance Learning

- 标题：Probabilistic Attention Based on Gaussian Processes for Deep Multiple Instance Learning
- 作者：Arne Schmidt, Pablo Morales-Álvarez, Rafael Molina
- 年份：2023
- 出版日期：2023-02-22
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks and Learning Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-237X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tnnls.2023.3245329
- OpenAlex ID：https://openalex.org/W4321487874
- 落地页：https://doi.org/10.1109/tnnls.2023.3245329
- 主主题：Image Retrieval and Classification Techniques
- 主题：Image Retrieval and Classification Techniques, AI in cancer detection, Machine Learning and Data Classification
- 关键词：Overfitting, Computer science, Artificial intelligence, Probabilistic logic, Machine learning, MNIST database, Gaussian process, Robustness (evolution), Deep learning, Gaussian, Uncertainty quantification, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Multiple instance learning (MIL) is a weakly supervised learning paradigm that is becoming increasingly popular because it requires less labeling effort than fully supervised methods. This is especially interesting for areas where the creation of large annotated datasets remains challenging, as in medicine. Although recent deep learning MIL approaches have obtained state-of-the-art results, they are fully deterministic and do not provide uncertainty estimations for the predictions. In this work, we introduce the attention Gaussian process (AGP) model, a novel probabilistic attention mechanism based on Gaussian processes (GPs) for deep MIL. AGP provides accurate bag-level predictions as well as instance-level explainability and can be trained end-to-end. Moreover, its probabilistic nature guarantees robustness to overfit on small datasets and uncertainty estimations for the predictions. The latter is especially important in medical applications, where decisions have a direct impact on the patient's health. The proposed model is validated experimentally as follows. First, its behavior is illustrated in two synthetic MIL experiments based on the well-known MNIST and CIFAR-10 datasets, respectively. Then, it is evaluated in three different real-world cancer detection experiments. AGP outperforms state-of-the-art MIL approaches, including deterministic deep learning ones. It shows a strong performance even on a small dataset with less than 100 labels and generalizes better than competing methods on an external test set. Moreover, we experimentally show that predictive uncertainty correlates with the risk of wrong predictions, and therefore it is a good indicator of reliability in practice. Our code is publicly available.

## 16652. WDAN: A Weighted Discriminative Adversarial Network With Dual Classifiers for Fine-Grained Open-Set Domain Adaptation

- 标题：WDAN: A Weighted Discriminative Adversarial Network With Dual Classifiers for Fine-Grained Open-Set Domain Adaptation
- 作者：Jing Li, Yang Liu, Qilong Wang, Qinghua Hu
- 年份：2023
- 出版日期：2023-02-27
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2023.3249200
- OpenAlex ID：https://openalex.org/W4322576840
- 落地页：https://doi.org/10.1109/tcsvt.2023.3249200
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Viral Infections and Vectors
- 关键词：Discriminative model, Computer science, Artificial intelligence, Categorization, Classifier (UML), Discriminator, Open set, Encoder, Machine learning, Artificial neural network, Pattern recognition (psychology), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep neural networks usually depend on substantial labeled data and suffer from poor generalization to new domains. Domain adaptation can be used to resolve these issues, using a classifier trained with a label-rich source and transferred to a label-scarce target domain. Traditional domain adaptation adopts the close-set assumption that both domains share the same classes. However, real-world applications operate in an open-set scenario where target domains have private categories. This aspect is considered by open-set domain adaptation (OSDA). Nevertheless, current OSDA benchmarks lack clear definitions of semantic classes that are at the core of the open-set concept. In this study, we propose fine-grained visual categorization (FGVC) datasets containing specific descriptions of semantic classes as a solution, introducing the new setting named fine-grained OSDA. Owing to the entanglement among FGVC, unknown class recognition, and domain adaptation, fine-grained OSDA is a challenging task. For this reason, we designed a weighted discriminative adversarial network with dual classifiers (WDAN). It utilizes a selective transformer encoder with overlapping patches and supervised contrastive learning to extract features suitable for FGVC, adversarial training with domain-specific discriminative information to recognize target-private classes, and a weighted conditional domain discriminator to learn domain-invariant features for domain adaptation. Extensive experiments on five benchmarks, including one newly built, demonstrated that WDAN outperforms state-of-the-art methods. This work fills the existing gap in benchmarks for fine-grained OSDA, promoting future developments of real-world applications.

## 16653. A Quantum-Classical Hybrid Solution for Deep Anomaly Detection

- 标题：A Quantum-Classical Hybrid Solution for Deep Anomaly Detection
- 作者：Maida Wang, Anqi Huang, Yong Liu, YI Xu-ming, Junjie Wu, Siqi Wang
- 年份：2023
- 出版日期：2023-02-27
- 类型：article
- 语言：en
- 来源：Entropy
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1099-4300
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/e25030427
- OpenAlex ID：https://openalex.org/W4322631367
- 落地页：https://doi.org/10.3390/e25030427
- 开放 PDF 链接：https://www.mdpi.com/1099-4300/25/3/427/pdf?version=1677491019
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Adversarial Robustness in Machine Learning, Machine Learning in Materials Science
- 关键词：Deep learning, Computer science, Artificial intelligence, Quantum, Deep neural networks, Inference, Anomaly (physics), Anomaly detection, Image (mathematics), Pattern recognition (psychology), Physics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Machine learning (ML) has achieved remarkable success in a wide range of applications. In recent ML research, deep anomaly detection (AD) has been a hot topic with the aim of discriminating among anomalous data with deep neural networks (DNNs). Notably, image AD is one of the most representative tasks in current deep AD research. ML's interaction with quantum computing is giving rise to a heated topic named quantum machine learning (QML), which enjoys great prospects according to recent academic research. This paper attempts to address the image AD problem in a deep manner with a novel QML solution. Specifically, we design a quantum-classical hybrid DNN (QHDNN) that aims to learn directly from normal raw images to train a normality model and then exclude images that do not conform to this model as anomalies during its inference. To enable the QHDNN to perform satisfactorily in deep image AD, we explore multiple quantum layer architectures and design a VQC-based QHDNN solution. Extensive experiments were conducted on commonly used benchmarks to test the proposed QML solution, whose results demonstrate the feasibility of addressing deep image AD with QML. Importantly, the experimental results show that our quantum-classical hybrid solution can even yield superior performance to that of its classical counterpart when they share the same number of learnable parameters.

## 16654. Facilitating innovation and knowledge transfer between homogeneous and heterogeneous datasets: Generic incremental transfer learning approach and multidisciplinary studies

- 标题：Facilitating innovation and knowledge transfer between homogeneous and heterogeneous datasets: Generic incremental transfer learning approach and multidisciplinary studies
- 作者：Kwok Tai Chui, Varsha Arya, Shahab S. Band, Mobeen Alhalabi, Ryan Wen Liu, Hao Ran
- 年份：2023
- 出版日期：2023-02-28
- 类型：article
- 语言：en
- 来源：Journal of Innovation & Knowledge
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2444-569X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1016/j.jik.2023.100313
- OpenAlex ID：https://openalex.org/W4322632461
- 落地页：https://doi.org/10.1016/j.jik.2023.100313
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Machine Learning and Data Classification, Machine Learning and ELM
- 关键词：Benchmark (surveying), Computer science, Transfer of learning, Machine learning, Artificial intelligence, Knowledge transfer, Multidisciplinary approach, Homogeneous, Domain (mathematical analysis), Data mining, Knowledge management, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Open datasets serve as facilitators for researchers to conduct research with ground truth data. Generally, datasets contain innovation and knowledge in the domains that could be transferred between homogeneous datasets and have become feasible using machine learning models with the advent of transfer learning algorithms. Research initiatives are drawn to the heterogeneous datasets if these could extract useful innovation and knowledge across datasets of different domains. A breakthrough can be achieved without the restriction requiring the similarities between datasets. A multiple incremental transfer learning is proposed to yield optimal results in the target model. A multiple rounds multiple incremental transfer learning with a negative transfer avoidance algorithm are proposed as a generic approach to transfer innovation and knowledge from the source domain to the target domain. Incremental learning has played an important role in lowering the risk of transferring unrelated information which reduces the performance of machine learning models. To evaluate the effectiveness of the proposed algorithm, multidisciplinary studies are carried out in 5 disciplines with 15 benchmark datasets. Each discipline comprises 3 datasets as studies with homogeneous datasets whereas heterogeneous datasets are formed between disciplines. The results reveal that the proposed algorithm enhances the average accuracy by 4.35% compared with existing works. Ablation studies are also conducted to analyse the contributions of the individual techniques of the proposed algorithm, namely, the multiple rounds strategy, incremental learning, and negative transfer avoidance algorithms. These techniques enhance the average accuracy of the machine learning model by 3.44%, 0.849%, and 4.26%, respectively.

## 16655. Shop by image: characterizing visual search in e-commerce

- 标题：Shop by image: characterizing visual search in e-commerce
- 作者：Arnon Dagan, Ido Guy, Slava Novgorodov
- 年份：2023
- 出版日期：2023-03-03
- 类型：article
- 语言：en
- 来源：Information Retrieval
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1386-4564
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1007/s10791-023-09418-1
- OpenAlex ID：https://openalex.org/W4323042875
- 落地页：https://doi.org/10.1007/s10791-023-09418-1
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s10791-023-09418-1.pdf
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Image Retrieval and Classification Techniques, Multimodal Machine Learning Applications
- 关键词：Computer science, Variety (cybernetics), Visual search, Information retrieval, Upload, Web search query, Popularity, Focus (optics), Segmentation, Domain (mathematical analysis), Query expansion, World Wide Web, Search engine, Artificial intelligence, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16656. Generative Inference Network for Imbalanced Domain Generalization

- 标题：Generative Inference Network for Imbalanced Domain Generalization
- 作者：Haifeng Xia, Taotao Jing, Zhengming Ding
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2023.3251103
- OpenAlex ID：https://openalex.org/W4323338785
- 落地页：https://doi.org/10.1109/tip.2023.3251103
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Machine Learning and Data Classification
- 关键词：Computer science, Generalization, Inference, Artificial intelligence, Discriminative model, Robustness (evolution), Domain (mathematical analysis), Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Domain generalization (DG) aims to learn transferable knowledge from multiple source domains and generalize it to the unseen target domain. To achieve such expectation, the intuitive solution is to seek domain-invariant representations via generative adversarial mechanism or minimization of cross-domain discrepancy. However, the widespread imbalanced data scale problem across source domains and category in real-world applications becomes the key bottleneck of improving generalization ability of model due to its negative effect on learning the robust classification model. Motivated by this observation, we first formulate a practical and challenging imbalance domain generalization (IDG) scenario, and then propose a straightforward but effective novel method generative inference network (GINet), which augments reliable samples for minority domain/category to promote discriminative ability of the learned model. Concretely, GINet utilizes the available cross-domain images from the identical category and estimates their common latent variable, which derives to discover domain-invariant knowledge for unseen target domain. According to these latent variables, our GINet further generates more novel samples with optimal transport constraint and deploys them to enhance the desired model with more robustness and generalization ability. Considerable empirical analysis and ablation studies on three popular benchmarks under normal DG and IDG setups suggests the advantage of our method over other DG methods on elevating model generalization. The source code is available in GitHub https://github.com/HaifengXia/IDG.

## 16657. Neighborhood Weighted Voting-Based Noise Correction for Crowdsourcing

- 标题：Neighborhood Weighted Voting-Based Noise Correction for Crowdsourcing
- 作者：Huiru Li, Liangxiao Jiang, Siqing Xue
- 年份：2023
- 出版日期：2023-03-11
- 类型：article
- 语言：en
- 来源：ACM Transactions on Knowledge Discovery from Data
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1556-4681
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/3586998
- OpenAlex ID：https://openalex.org/W4323925706
- 落地页：https://doi.org/10.1145/3586998
- 主主题：Mobile Crowdsensing and Crowdsourcing
- 主题：Mobile Crowdsensing and Crowdsourcing, Machine Learning and Data Classification, Data Stream Mining Techniques
- 关键词：Crowdsourcing, Noise (video), Majority rule, Computer science, Ground truth, Artificial intelligence, Metric (unit), Inference, Set (abstract data type), Filter (signal processing), Voting, Machine learning, Noise measurement, Feature (linguistics), Pattern recognition (psychology), Data mining, Algorithm, Noise reduction, Computer vision, Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In crowdsourcing scenarios, we can obtain each instance’s multiple noisy labels set from different crowd workers and then use a ground truth inference algorithm to infer its integrated label. Despite the effectiveness of ground truth inference algorithms, a certain level of noise still remains in the integrated labels. To reduce the impact of noise, many noise correction algorithms have been proposed in recent years. To the best of our knowledge, however, nearly all existing noise correction algorithms only exploit each instance’s own multiple noisy label sets but ignore the multiple noisy label sets of its neighbors. Here neighbors refer to the nearest instances found in the feature space based on the distance metric learning. In this article, we propose neighborhood weighted voting-based noise correction (NWVNC). In NWVNC, we at first take advantage of the multiple noisy label sets of each instance’s neighbors (including itself) to estimate the probability that it belongs to its integrated label. Then, we use the estimated probability to identify and filter noise instances and thus obtain a clean set and a noise set. Finally, we train three heterogeneous classifiers on the clean set and correct the noise instances by the consensus voting of three trained classifiers. The experimental results on 34 simulated and two real-world crowdsourced datasets show that NWVNC significantly outperforms all the other state-of-the-art noise correction algorithms used for comparison.

## 16658. Adversarial superiority in android malware detection: Lessons from reinforcement learning based evasion attacks and defenses

- 标题：Adversarial superiority in android malware detection: Lessons from reinforcement learning based evasion attacks and defenses
- 作者：Hemant Rathore, Adarsh Nandanwar, Sanjay K. Sahay, Mohit Sewak
- 年份：2023
- 出版日期：2023-03-01
- 类型：article
- 语言：en
- 来源：Forensic Science International Digital Investigation
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2666-2817
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.fsidi.2023.301511
- OpenAlex ID：https://openalex.org/W4327939473
- 落地页：https://doi.org/10.1016/j.fsidi.2023.301511
- 主主题：Advanced Malware Detection Techniques
- 主题：Advanced Malware Detection Techniques, Adversarial Robustness in Machine Learning, Software Testing and Debugging Techniques
- 关键词：Malware, Android malware, Adversarial system, Computer science, Evasion (ethics), Android (operating system), Adversary, Exploit, Cryptovirology, Computer security, Reinforcement learning, Artificial intelligence, Permission, Machine learning, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Today, android smartphones are being used by billions of users and thus have become a lucrative target of malware designers. Therefore being one step ahead in this zero-sum game of malware detection between the anti-malware community and malware developers is more of a necessity than a desire. This work focuses on a proactive adversary-aware framework to develop adversarially superior android malware detection models. We first investigate the adversarial robustness of thirty-six distinct malware detection models constructed using two static features (permission and intent) and eighteen classification algorithms. We designed two Targeted Type-II Evasion Attacks (TRPO-MalEAttack and PPO-MalEAttack) based on reinforcement learning to exploit vulnerabilities in the above malware detection models. The attacks aim to add minimum perturbations in each malware application and convert it into an adversarial application that can fool the malware detection models. The TRPO-MalEAttack achieves an average fooling rate of 95.75% (with 2.02 mean perturbations), reducing the average accuracy from 86.01% to 49.11% in thirty-six malware detection models. On the other hand, The PPO-MalEAttack achieves a higher average fooling rate of 96.87% (with 2.08 mean perturbations), reducing the average accuracy from 86.01% to 48.65% in the same thirty-six detection models. We also develop a list of the TEN most vulnerable android permissions and intents that an adversary can use to generate more adversarial applications. Later, we propose a defense strategy (MalVPatch) to counter the adversarial attacks on malware detection models. The MalVPatch defense achieves higher detection accuracy along with a drastic improvement in the adversarial robustness of malware detection models. Finally, we conclude that investigating the adversarial robustness of models is necessary before their real-world deployment and helps achieve adversarial superiority in android malware detection.

## 16659. A black-box reversible adversarial example for authorizable recognition to shared images

- 标题：A black-box reversible adversarial example for authorizable recognition to shared images
- 作者：Lizhi Xiong, Yue Wu, Peipeng Yu, Yuhui Zheng
- 年份：2023
- 出版日期：2023-03-21
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2023.109549
- OpenAlex ID：https://openalex.org/W4328053092
- 落地页：https://doi.org/10.1016/j.patcog.2023.109549
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Digital Media Forensic Detection, Advanced Steganography and Watermarking Techniques
- 关键词：Adversarial system, Computer science, Damages, Deep neural networks, Scheme (mathematics), Computer security, Image (mathematics), Usability, Black box, The Internet, Artificial intelligence, Artificial neural network, Internet privacy, Law, Human–computer interaction, World Wide Web, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16660. Fully and Weakly Supervised Referring Expression Segmentation With End-to-End Learning

- 标题：Fully and Weakly Supervised Referring Expression Segmentation With End-to-End Learning
- 作者：Hui Li, Ming-Jie Sun, Jimin Xiao, Eng Gee Lim, Yao Zhao
- 年份：2023
- 出版日期：2023-03-31
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2023.3263468
- OpenAlex ID：https://openalex.org/W4361983876
- 落地页：https://doi.org/10.1109/tcsvt.2023.3263468
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Natural Language Processing Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Segmentation, Computer science, Artificial intelligence, Pipeline (software), Pattern recognition (psychology), Benchmark (surveying), Margin (machine learning), Feature (linguistics), Object (grammar), Kernel (algebra), Supervised learning, Expression (computer science), Computer vision, Machine learning, Artificial neural network, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Referring Expression Segmentation (RES), which is aimed at localizing and segmenting the target according to the given language expression, has drawn increasing attention. Existing methods jointly consider the localization and segmentation steps, which rely on the fused visual and linguistic features for both steps. We argue that the conflict between the purpose of identifying an object and generating a mask limits the RES performance. To solve this problem, we propose a parallel position-kernel-segmentation pipeline to better isolate and then interact the localization and segmentation steps. In our pipeline, linguistic information will not directly contaminate the visual feature for segmentation. Specifically, the localization step localizes the target object in the image based on the referring expression, and then the visual kernel obtained from the localization step guides the segmentation step. This pipeline also enables us to train RES in a weakly-supervised way, where the pixel-level segmentation labels are replaced by click annotations on center and corner points. The position head is fully-supervised and trained with the click annotations as supervision, and the segmentation head is trained with weakly-supervised segmentation losses. To validate our framework on a weakly-supervised setting, we annotated three RES benchmark datasets (RefCOCO, RefCOCO+ and RefCOCOg) with click annotations. Our method is simple but surprisingly effective, outperforming all previous state-of-the-art RES methods on fully- and weakly-supervised settings by a large margin. The code and dataset will be released on <uri xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">https://github.com/detectiveli/PKS.git</uri> .

## 16661. Differential evolution based dual adversarial camouflage: Fooling human eyes and object detectors

- 标题：Differential evolution based dual adversarial camouflage: Fooling human eyes and object detectors
- 作者：Jialiang Sun, Wen Yao, Tingsong Jiang, Donghua Wang, Xiaoqian Chen
- 年份：2023
- 出版日期：2023-03-31
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neunet.2023.03.041
- OpenAlex ID：https://openalex.org/W4362474101
- 落地页：https://doi.org/10.1016/j.neunet.2023.03.041
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Image Processing Techniques and Applications, Advanced Image Processing Techniques
- 关键词：Camouflage, Computer science, Artificial intelligence, Object (grammar), Computer vision, Object detection, Detector, Adversarial system, Adaptation (eye), Human eye, Pattern recognition (psychology), Optics, Physics, Telecommunications
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16662. Multi-Modal Fake News Detection via Bridging the Gap between Modals

- 标题：Multi-Modal Fake News Detection via Bridging the Gap between Modals
- 作者：Peng Liu, Wenhua Qian, Dan Xu, Bingling Ren, Jinde Cao
- 年份：2023
- 出版日期：2023-04-04
- 类型：article
- 语言：en
- 来源：Entropy
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1099-4300
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/e25040614
- OpenAlex ID：https://openalex.org/W4362619048
- 落地页：https://doi.org/10.3390/e25040614
- 开放 PDF 链接：https://www.mdpi.com/1099-4300/25/4/614/pdf?version=1680603380
- 主主题：Misinformation and Its Impacts
- 主题：Misinformation and Its Impacts, Multimodal Machine Learning Applications, Topic Modeling
- 关键词：Computer science, Leverage (statistics), Bridging (networking), Modal, Semantic gap, Information retrieval, Representation (politics), Image (mathematics), Fuse (electrical), Artificial intelligence, Natural language processing, Image retrieval
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Multi-modal fake news detection aims to identify fake information through text and corresponding images. The current methods purely combine images and text scenarios by a vanilla attention module but there exists a semantic gap between different scenarios. To address this issue, we introduce an image caption-based method to enhance the model's ability to capture semantic information from images. Formally, we integrate image description information into the text to bridge the semantic gap between text and images. Moreover, to optimize image utilization and enhance the semantic interaction between images and text, we combine global and object features from the images for the final representation. Finally, we leverage a transformer to fuse the above multi-modal content. We carried out extensive experiments on two publicly available datasets, and the results show that our proposed method significantly improves performance compared to other existing methods.

## 16663. Who evaluates the evaluators? On automatic metrics for assessing AI-based offensive code generators

- 标题：Who evaluates the evaluators? On automatic metrics for assessing AI-based offensive code generators
- 作者：Pietro Liguori, Cristina Improta, Roberto Natella, Bojan Čukić, Domenico Cotroneo
- 年份：2023
- 出版日期：2023-04-13
- 类型：article
- 语言：en
- 来源：Expert Systems with Applications
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0957-4174
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.eswa.2023.120073
- OpenAlex ID：https://openalex.org/W4365452590
- 落地页：https://doi.org/10.1016/j.eswa.2023.120073
- 主主题：Software Engineering Research
- 主题：Software Engineering Research, Advanced Malware Detection Techniques, Adversarial Robustness in Machine Learning
- 关键词：Offensive, Computer science, Metric (unit), Code (set theory), Artificial intelligence, Python (programming language), Machine translation, Similarity (geometry), Machine learning, Natural language processing, Natural language, Source code, Set (abstract data type), Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
AI-based code generators are an emerging solution for automatically writing programs starting from descriptions in natural language, by using deep neural networks (Neural Machine Translation, NMT). In particular, code generators have been used for ethical hacking and offensive security testing by generating proof-of-concept attacks. Unfortunately, the evaluation of code generators still faces several issues. The current practice uses output similarity metrics, i.e., automatic metrics that compute the textual similarity of generated code with ground-truth references. However, it is not clear what metric to use, and which metric is most suitable for specific contexts. This work analyzes a large set of output similarity metrics on offensive code generators. We apply the metrics on two state-of-the-art NMT models using two datasets containing offensive assembly and Python code with their descriptions in the English language. We compare the estimates from the automatic metrics with human evaluation and provide practical insights into their strengths and limitations.

## 16664. A domain-specific language for describing machine learning datasets

- 标题：A domain-specific language for describing machine learning datasets
- 作者：Joan Giner-Miguelez, Abel Gómez, Jordi Cabot
- 年份：2023
- 出版日期：2023-05-02
- 类型：article
- 语言：en
- 来源：Journal of Computer Languages
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2590-1184
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.cola.2023.101209
- OpenAlex ID：https://openalex.org/W4367673256
- 落地页：https://doi.org/10.1016/j.cola.2023.101209
- 主主题：Scientific Computing and Data Management
- 主题：Scientific Computing and Data Management, Topic Modeling, Machine Learning and Data Classification
- 关键词：Digital subscriber line, Computer science, Plug-in, Leverage (statistics), Domain (mathematical analysis), Artificial intelligence, Machine learning, License, Source code, Domain-specific language, XML, Natural language processing, Data science, Software engineering, Programming language, World Wide Web
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Datasets are essential for training and evaluating machine learning (ML) models. However, they are also at the root of many undesirable model behaviors, such as biased predictions. To address this issue, the machine learning community is proposing a data-centric cultural shift , where data issues are given the attention they deserve and more standard practices for gathering and describing datasets are discussed and established. So far, these proposals are mostly high-level guidelines described in natural language and, as such, they are difficult to formalize and apply to particular datasets. In this sense, and inspired by these proposals, we define a new domain-specific language (DSL) to precisely describe machine learning datasets in terms of their structure, provenance, and social concerns. We believe this DSL will facilitate any ML initiative to leverage and benefit from this data-centric shift in ML (e.g., selecting the most appropriate dataset for a new project or better replicating other ML results). The DSL is implemented as a Visual Studio Code plugin, and it has been published under an open-source license. • Data issues in ML raise the community’s interest in building data best practices. • This work proposes a structured language to describe machine learning datasets. • The language allows describing composition, provenance, and social concerns of data. • A structured format eases the dataset comparison and the replication of ML results. • The language is supported by DescribeML, a VSCode tool to aid in its usage.

## 16665. A novel method for image captioning using multimodal feature fusion employing mask RNN and LSTM models

- 标题：A novel method for image captioning using multimodal feature fusion employing mask RNN and LSTM models
- 作者：Kumaravel Thangavel, Natesan Palanisamy, Suresh Muthusamy, Om Prava Mishra, Suma Christal Mary Sundararajan, Hitesh Panchal, Ashok Kumar Loganathan, Ponarun Ramamoorthi
- 年份：2023
- 出版日期：2023-05-22
- 类型：article
- 语言：en
- 来源：Soft Computing
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1432-7643
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00500-023-08448-7
- OpenAlex ID：https://openalex.org/W4377226998
- 落地页：https://doi.org/10.1007/s00500-023-08448-7
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Advanced Neural Network Applications
- 关键词：Closed captioning, Computer science, Artificial intelligence, Convolutional neural network, Deep learning, Feature (linguistics), Recurrent neural network, Coding (social sciences), Decoding methods, Pattern recognition (psychology), Salient, Feature extraction, Machine learning, Artificial neural network, Image (mathematics), Natural language processing
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16666. Concept Parser With Multimodal Graph Learning for Video Captioning

- 标题：Concept Parser With Multimodal Graph Learning for Video Captioning
- 作者：Bofeng Wu, Buyu Liu, Peng Huang, Jun Bao, Xi Peng, Jun Yu
- 年份：2023
- 出版日期：2023-05-22
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Circuits and Systems for Video Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1051-8215
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcsvt.2023.3277827
- OpenAlex ID：https://openalex.org/W4377235499
- 落地页：https://doi.org/10.1109/tcsvt.2023.3277827
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Advanced Image and Video Retrieval Techniques
- 关键词：Computer science, Transformer, Closed captioning, Parsing, Exploit, Ground truth, Graph, Artificial intelligence, Speech recognition, Theoretical computer science, Image (mathematics), Voltage
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Conventional video captioning methods are either stage-wise or simple end-to-end. While the former might introduce additional noise when exploiting off-the-shelf models to provide extra information, the latter suffers from lacking high-level cues. Therefore, a more desired framework should be able to capture multi-aspects of videos consistently. To this end, we present a concept-aware and task-specific model named CAT that accounts for both low-level visual and high-level concept cues, and incorporates them effectively in an end-to-end manner. Specifically, low-level visual and high-level concept features are obtained from the video transformer and concept parser of CAT. And a concept loss is further introduced to regularize the learning process of concept parser w.r.t. generated pseudo ground truth. To combine multi-level features, a caption transformer is later introduced in CAT, where visual and concept features are the inputs and caption is its output. In particular, we make critical design choices in the caption transformer to learn to exploit these cues with a multi-modal graph. This is achieved by a graph loss that enforces effective learning of intra and inter correlations between multi-level cues. Extensive experiments on three benchmark datasets demonstrate that CAT achieves 2.3 and 0.7 improvements in the CIDEr metric on MSVD and MSR-VTT compared to the state-of-the-art method SwinBERT and also achieves a competitive result on VATEX.

## 16667. Universal backdoor attack on deep neural networks for malware detection

- 标题：Universal backdoor attack on deep neural networks for malware detection
- 作者：Yunchun Zhang, Fan Feng, Zikun Liao, Zixuan Li, Shaowen Yao
- 年份：2023
- 出版日期：2023-05-25
- 类型：article
- 语言：en
- 来源：Applied Soft Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1568-4946
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.asoc.2023.110389
- OpenAlex ID：https://openalex.org/W4378189129
- 落地页：https://doi.org/10.1016/j.asoc.2023.110389
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Anomaly Detection Techniques and Applications
- 关键词：Backdoor, Computer science, Deep learning, Byte, Malware, Artificial intelligence, Artificial neural network, Convolutional neural network, Pattern recognition (psychology), Computer security, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16668. GNN Cleaner: Label Cleaner for Graph Structured Data

- 标题：GNN Cleaner: Label Cleaner for Graph Structured Data
- 作者：Jun Xia, Haitao Lin, Yongjie Xu, Cheng Tan, Lirong Wu, Siyuan Li, Stan Z. Li
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Knowledge and Data Engineering
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：1041-4347
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tkde.2023.3288002
- OpenAlex ID：https://openalex.org/W4381327774
- 落地页：https://doi.org/10.1109/tkde.2023.3288002
- 主主题：Advanced Graph Neural Networks
- 主题：Advanced Graph Neural Networks, Machine Learning and Data Classification, Text and Document Classification Technologies
- 关键词：Robustness (evolution), Computer science, Exploit, Graph, Noisy data, Artificial intelligence, Machine learning, Data mining, Training set, Artificial neural network, Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Graph Neural Network (GNN) has emerged as a predominant tool for graph data analysis. Despite their proliferation, the low-quality labels of many real-world graphs will undermine their performance dramatically. Existing studies on learning neural networks with noisy labels mainly focus on independent data and thus cannot fully exploit the structural information of graph data. Currently, there are few studies of robustness to noisy labels for graph-structured data even if this problem is commonly seen in real-world settings. To remedy this deficiency, we propose <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">GNN Cleaner</i> which utilizes structural information of graph data to combat noisy labels. More specifically, a pseudo label is computed from the neighboring labels for each node in the training set via a modified version of label propagation. Additionally, a novel method is developed to learn to correct the labels adaptively and dynamically. Extensive experiments show that GNN Cleaner can train GNNs robustly and correct both the synthetic and real-world noisy labels even if the noise is severe. Moreover, GNN Cleaner is model-agnostic and can be combined with various GNNs to improve their robustness against label noise.

## 16669. Visual Writing Prompts: Character-Grounded Story Generation with Curated Image Sequences

- 标题：Visual Writing Prompts: Character-Grounded Story Generation with Curated Image Sequences
- 作者：Xudong Hong, Asad Sayeed, Khushboo Mehra, Vera Demberg, Bernt Schiele
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：Transactions of the Association for Computational Linguistics
- 来源类型：journal
- 出版方：Association for Computational Linguistics
- ISSN-L：2307-387X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1162/tacl_a_00553
- OpenAlex ID：https://openalex.org/W4381611941
- 落地页：https://doi.org/10.1162/tacl_a_00553
- 开放 PDF 链接：https://direct.mit.edu/tacl/article-pdf/doi/10.1162/tacl_a_00553/2134487/tacl_a_00553.pdf
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Video Analysis and Summarization, Advanced Image and Video Retrieval Techniques
- 关键词：Computer science, Image (mathematics), Grounded theory, Sequence (biology), Set (abstract data type), Code (set theory), Coherence (philosophical gambling strategy), Character (mathematics), Crowdsourcing, Image file formats, Artificial intelligence, Visualization, World Wide Web, Programming language, Qualitative research
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Current work on image-based story generation suffers from the fact that the existing image sequence collections do not have coherent plots behind them. We improve visual story generation by producing a new image-grounded dataset, Visual Writing Prompts (VWP). VWP contains almost 2K selected sequences of movie shots, each including 5-10 images. The image sequences are aligned with a total of 12K stories which were collected via crowdsourcing given the image sequences and a set of grounded characters from the corresponding image sequence. Our new image sequence collection and filtering process has allowed us to obtain stories that are more coherent, diverse, and visually grounded compared to previous work. We also propose a character-based story generation model driven by coherence as a strong baseline. Evaluations show that our generated stories are more coherent, visually grounded, and diverse than stories generated with the current state-of-the-art model. Our code, image features, annotations and collected stories are available at https://vwprompt.github.io/.

## 16670. On the Robustness of Random Forest Against Untargeted Data Poisoning: An Ensemble-Based Approach

- 标题：On the Robustness of Random Forest Against Untargeted Data Poisoning: An Ensemble-Based Approach
- 作者：Marco Anisetti, Claudio A. Ardagna, Alessandro Balestrucci, Nicola Bena, Ernesto Damiani, Chan Yeob Yeun
- 年份：2023
- 出版日期：2023-07-07
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Sustainable Computing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2377-3782
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tsusc.2023.3293269
- OpenAlex ID：https://openalex.org/W4383503685
- 落地页：https://doi.org/10.1109/tsusc.2023.3293269
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Network Security and Intrusion Detection, Anomaly Detection Techniques and Applications
- 关键词：Random forest, Robustness (evolution), Computer science, Ensemble learning, Machine learning, Ensemble forecasting, Artificial intelligence, Boosting (machine learning), Training set, Gradient boosting, Leverage (statistics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Machine learning is becoming ubiquitous. From finance to medicine, machine learning models are boosting decision/making processes and even outperforming humans in some tasks. This huge progress in terms of prediction quality does not however find a counterpart in the security of such models and corresponding predictions, where perturbations of fractions of the training set (poisoning) can seriously undermine the model accuracy. Research on poisoning attacks and defenses received increasing attention in the last decade, leading to several promising solutions aiming to increase the robustness of machine learning. Among them, ensemble-based defenses, where different models are trained on portions of the training set and their predictions are then aggregated, provide strong theoretical guarantees at the price of a linear overhead. Surprisingly, ensemble-based defenses, which do not pose any restrictions on the base model, have not been applied to increase the robustness of random forest models. The work in this paper aims to fill in this gap by designing and implementing a novel hash-based ensemble approach that protects random forest against untargeted, random poisoning attacks. An extensive experimental evaluation measures the performance of our approach against a variety of attacks, as well as its sustainability in terms of resource consumption and performance, and compares it with a traditional monolithic model based on random forest. A final discussion presents our main findings and compares our approach with existing poisoning defenses targeting random forests.

## 16671. An ensemble machine learning approach for classification tasks using feature generation

- 标题：An ensemble machine learning approach for classification tasks using feature generation
- 作者：Wenjuan Feng, Jin Gou, Zongwen Fan, Xiang Chen
- 年份：2023
- 出版日期：2023-07-11
- 类型：article
- 语言：en
- 来源：Connection Science
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0954-0091
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1080/09540091.2023.2231168
- OpenAlex ID：https://openalex.org/W4383875329
- 落地页：https://doi.org/10.1080/09540091.2023.2231168
- 开放 PDF 链接：https://www.tandfonline.com/doi/pdf/10.1080/09540091.2023.2231168?download=true
- 主主题：Time Series Analysis and Forecasting
- 主题：Time Series Analysis and Forecasting, Anomaly Detection Techniques and Applications, Machine Learning and Data Classification
- 关键词：Computer science, Artificial intelligence, Classifier (UML), Support vector machine, Machine learning, Linear classifier, Pattern recognition (psychology), Feature selection, Binary classification, Ensemble learning, Random subspace method, One-class classification, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Although machine learning classifiers have been successfully used in the medical and engineering fields, there is still room for improving the predictive accuracy of model classification. The higher the accuracy of the classifier, the better suggestions can be provided for the decision makers. Therefore, in this study, we propose an ensemble machine learning approach, called Feature generation-based Ensemble Support Vector Machine (FESVM), for classification tasks. We first apply the feature selection technique to select the most related features. Next, we introduce an ensemble strategy to aggregate multiple base estimators for the final prediction using the meta-classifier SVM. During this stage, we use the classification probabilities obtained from the base classifier to generate new features. After that, the generated features are added to the original data set to form a new data set. Finally, this new data set is utilised to train the meta-classifier SVM to obtain the final classification results. For example, for a binary classification task, each base classifier has two probabilities (p for one class and 1−p for the other class). In this case, two new features are generated from the combination of probabilities based on these base classifiers. One is the sum of p as new feature 1, and the other is the sum of 1−p as new feature 2. These two new features are then added to the original data set to form the new data set. In the same way, our feature generation method can be easily extended for a multi-class task for generating new features, where the number of features depends on the number of classes. Those generated features from the base estimators (first layer) are added to the original data set to form a new data set. This new data set is used as the input to the second layer (meta-classifier) to obtain the final model. Experiments based on the 20 data sets show that our proposed model FESVM has the best performance compared to the other machine learning classifiers under comparison. In addition, our FESVM has better performance than the original stacking method in the multi-class classification tasks. Statistical results based on the Wilcoxon–Holm method also confirms that our FESVM can significantly outperform the other models. These indicate that our FESVM can be a useful tool for classification tasks, especially multi-classification tasks.

## 16672. K-PathVQA: Knowledge-Aware Multimodal Representation for Pathology Visual Question Answering

- 标题：K-PathVQA: Knowledge-Aware Multimodal Representation for Pathology Visual Question Answering
- 作者：Usman Naseem, Matloob Khushi, Adam G. Dunn, Jinman Kim
- 年份：2023
- 出版日期：2023-07-11
- 类型：article
- 语言：en
- 来源：IEEE Journal of Biomedical and Health Informatics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2168-2194
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/jbhi.2023.3294249
- OpenAlex ID：https://openalex.org/W4383899673
- 落地页：https://doi.org/10.1109/jbhi.2023.3294249
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Topic Modeling, Domain Adaptation and Few-Shot Learning
- 关键词：Generalizability theory, Computer science, Question answering, Knowledge base, Artificial intelligence, Representation (politics), Natural language processing, Information retrieval, Task (project management), Medical knowledge, Knowledge graph, Visualization, Graph, Medicine, Theoretical computer science, Psychology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Pathology imaging is routinely used to detect the underlying effects and causes of diseases or injuries. Pathology visual question answering (PathVQA) aims to enable computers to answer questions about clinical visual findings from pathology images. Prior work on PathVQA has focused on directly analyzing the image content using conventional pretrained encoders without utilizing relevant external information when the image content is inadequate. In this paper, we present a knowledge-driven PathVQA (K-PathVQA), which uses a medical knowledge graph (KG) from a complementary external structured knowledge base to infer answers for the PathVQA task. K-PathVQA improves the question representation with external medical knowledge and then aggregates vision, language, and knowledge embeddings to learn a joint knowledge-image-question representation. Our experiments using a publicly available PathVQA dataset showed that our K-PathVQA outperformed the best baseline method with an increase of 4.15% in accuracy for the overall task, an increase of 4.40% in open-ended question type and an absolute increase of 1.03% in closed-ended question types. Ablation testing shows the impact of each of the contributions. Generalizability of the method is demonstrated with a separate medical VQA dataset.

## 16673. Why technical solutions for detecting AI-generated content in research and education are insufficient

- 标题：Why technical solutions for detecting AI-generated content in research and education are insufficient
- 作者：Jahna Otterbacher
- 年份：2023
- 出版日期：2023-07-01
- 类型：article
- 语言：en
- 来源：Patterns
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2666-3899
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1016/j.patter.2023.100796
- OpenAlex ID：https://openalex.org/W4384343990
- 落地页：https://doi.org/10.1016/j.patter.2023.100796
- 开放 PDF 链接：http://www.cell.com/article/S2666389923001514/pdf
- 主主题：Artificial Intelligence in Healthcare and Education
- 主题：Artificial Intelligence in Healthcare and Education, Explainable Artificial Intelligence (XAI), Machine Learning and Data Classification
- 关键词：Content (measure theory), Computer science, Process engineering, Engineering, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Rather than "fighting" AI with more AI, we must develop an academic culture that promotes the use of generative AI in a creative, ethical manner.

## 16674. Lifelong Learning With Cycle Memory Networks

- 标题：Lifelong Learning With Cycle Memory Networks
- 作者：Jian Peng, Dingqi Ye, Bo Tang, Yinjie Lei, Yu Liu, Haifeng Li
- 年份：2023
- 出版日期：2023-07-28
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks and Learning Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-237X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tnnls.2023.3294495
- OpenAlex ID：https://openalex.org/W4385338523
- 落地页：https://doi.org/10.1109/tnnls.2023.3294495
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications
- 关键词：Forgetting, Computer science, Artificial intelligence, Memorization, Knowledge transfer, Task (project management), Knowledge management, Cognitive psychology, Psychology, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Learning from a sequence of tasks for a lifetime is essential for an agent toward artificial general intelligence. Despite the explosion of this research field in recent years, most work focuses on the well-known catastrophic forgetting issue. In contrast, this work aims to explore knowledge-transferable lifelong learning without storing historical data and significant additional computational overhead. We demonstrate that existing data-free frameworks, including regularization-based single-network and structure-based multinetwork frameworks, face a fundamental issue of lifelong learning, named anterograde forgetting, i.e., preserving and transferring memory may inhibit the learning of new knowledge. We attribute it to the fact that the learning network capacity decreases while memorizing historical knowledge and conceptual confusion between the irrelevant old knowledge and the current task. Inspired by the complementary learning theory in neuroscience, we endow artificial neural networks with the ability to continuously learn without forgetting while recalling historical knowledge to facilitate learning new knowledge. Specifically, this work proposes a general framework named cycle memory networks (CMNs). The CMN consists of two individual memory networks to store short- and long-term memories separately to avoid capacity shrinkage and a transfer cell between them. It enables knowledge transfer from the long-term to the short-term memory network to mitigate conceptual confusion. In addition, the memory consolidation mechanism integrates short-term knowledge into the long-term memory network for knowledge accumulation. We demonstrate that the CMN can effectively address the anterograde forgetting on several task-related, task-conflict, class-incremental, and cross-domain benchmarks. Furthermore, we provide extensive ablation studies to verify each framework component. The source codes are available at: https://github.com/GeoX-Lab/CMN.

## 16675. Jacobian norm with Selective Input Gradient Regularization for interpretable adversarial defense

- 标题：Jacobian norm with Selective Input Gradient Regularization for interpretable adversarial defense
- 作者：Deyin Liu, Lin Wu, Bo Li, Farid Boussaïd, Mohammed Bennamoun, Xianghua Xie, Chengwu Liang
- 年份：2023
- 出版日期：2023-08-22
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1016/j.patcog.2023.109902
- OpenAlex ID：https://openalex.org/W4386074714
- 落地页：https://doi.org/10.1016/j.patcog.2023.109902
- 开放 PDF 链接：https://www.sciencedirect.com/science/article/pii/S0031320323006003
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Explainable Artificial Intelligence (XAI), Anomaly Detection Techniques and Applications
- 关键词：Interpretability, Adversarial system, Computer science, Jacobian matrix and determinant, Deep neural networks, Artificial intelligence, Machine learning, Robustness (evolution), Regularization (linguistics), Deep learning, Norm (philosophy), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16676. Towards Defending Multiple $$\ell _p$$-Norm Bounded Adversarial Perturbations via Gated Batch Normalization

- 标题：Towards Defending Multiple $$\ell _p$$-Norm Bounded Adversarial Perturbations via Gated Batch Normalization
- 作者：Aishan Liu, Shiyu Tang, Xinyun Chen, Lei Huang, Haotong Qin, Xianglong Liu, Dacheng Tao
- 年份：2023
- 出版日期：2023-09-04
- 类型：article
- 语言：en
- 来源：International Journal of Computer Vision
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0920-5691
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11263-023-01884-w
- OpenAlex ID：https://openalex.org/W4386421331
- 落地页：https://doi.org/10.1007/s11263-023-01884-w
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications
- 关键词：Adversarial system, Bounded function, Perturbation (astronomy), Normalization (sociology), MNIST database, Norm (philosophy), Mathematics, Computer science, Artificial neural network, Algorithm, Combinatorics, Artificial intelligence, Physics, Mathematical analysis
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16677. Generative Adversarial Network (GAN)-Based Autonomous Penetration Testing for Web Applications

- 标题：Generative Adversarial Network (GAN)-Based Autonomous Penetration Testing for Web Applications
- 作者：Ankur Chowdhary, Kritshekhar Jha, Ming Zhao
- 年份：2023
- 出版日期：2023-09-21
- 类型：article
- 语言：en
- 来源：Sensors
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1424-8220
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/s23188014
- OpenAlex ID：https://openalex.org/W4386917822
- 落地页：https://doi.org/10.3390/s23188014
- 开放 PDF 链接：https://www.mdpi.com/1424-8220/23/18/8014/pdf?version=1695307152
- 主主题：Advanced Malware Detection Techniques
- 主题：Advanced Malware Detection Techniques, Network Security and Intrusion Detection, Adversarial Robustness in Machine Learning
- 关键词：Cross-site scripting, Computer science, SQL injection, Fuzz testing, Scripting language, Application firewall, Taint checking, Web application security, Web application, Attack surface, Stateful firewall, Computer security, The Internet, World Wide Web, Software, Web development, Search engine, Network packet, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The web application market has shown rapid growth in recent years. The expansion of Wireless Sensor Networks (WSNs) and the Internet of Things (IoT) has created new web-based communication and sensing frameworks. Current security research utilizes source code analysis and manual exploitation of web applications, to identify security vulnerabilities, such as Cross-Site Scripting (XSS) and SQL Injection, in these emerging fields. The attack samples generated as part of web application penetration testing on sensor networks can be easily blocked, using Web Application Firewalls (WAFs). In this research work, we propose an autonomous penetration testing framework that utilizes Generative Adversarial Networks (GANs). We overcome the limitations of vanilla GANs by using conditional sequence generation. This technique helps in identifying key features for XSS attacks. We trained a generative model based on attack labels and attack features. The attack features were identified using semantic tokenization, and the attack payloads were generated using conditional sequence GAN. The generated attack samples can be used to target web applications protected by WAFs in an automated manner. This model scales well on a large-scale web application platform, and it saves the significant effort invested in manual penetration testing.

## 16678. GrASPE: Graph Based Multimodal Fusion for Robot Navigation in Outdoor Environments

- 标题：GrASPE: Graph Based Multimodal Fusion for Robot Navigation in Outdoor Environments
- 作者：Kasun Weerakoon, Adarsh Jagan Sathyamoorthy, Jing Liang, Tianrui Guan, Utsav Patel, Dinesh Manocha
- 年份：2023
- 出版日期：2023-09-27
- 类型：article
- 语言：en
- 来源：IEEE Robotics and Automation Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2377-3766
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/lra.2023.3320013
- OpenAlex ID：https://openalex.org/W4387092523
- 落地页：https://doi.org/10.1109/lra.2023.3320013
- 主主题：Robotic Path Planning Algorithms
- 主题：Robotic Path Planning Algorithms, Multimodal Machine Learning Applications, Robotics and Sensor-Based Localization
- 关键词：Computer science, Artificial intelligence, Odometry, Robot, Computer vision, Sensor fusion, Point cloud, Graph, Feature (linguistics), Mobile robot
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We present a novel trajectory traversability estimation and planning algorithm for robot navigation in complex outdoor environments. We incorporate multimodal sensory inputs from an RGB camera, 3D LiDAR, and the robot's odometry sensor to train a prediction model to estimate candidate trajectories' success probabilities based on partially reliable multi-modal sensor observations. We encode high-dimensional multi-modal sensory inputs to low-dimensional feature vectors using encoder networks and represent them as a connected graph. The graph is then used to train an attention-based Graph Neural Network (GNN) to predict trajectory success probabilities. We further analyze the number of features in the image (corners) and point cloud data (edges and planes) separately to quantify their reliability to augment the weights of the feature graph representation used in our GNN. During runtime, our model utilizes multi-sensor inputs to predict the success probabilities of the trajectories generated by a local planner to avoid potential collisions and failures. Our algorithm demonstrates robust predictions when one or more sensor modalities are unreliable or unavailable in complex outdoor environments. We evaluate our algorithm's navigation performance using a Spot robot in real-world outdoor environments. We observe an increase of 10-30% in terms of navigation success rate and up to 15% increase in AU-ROC compared to the state-of-the-art navigation methods.

## 16679. An Intelligent Edge-Cloud Collaborative Framework for Communication Security in Distributed Cyber-Physical Systems

- 标题：An Intelligent Edge-Cloud Collaborative Framework for Communication Security in Distributed Cyber-Physical Systems
- 作者：Cen Chen, Yangfan Li, Qinyu Wang, Xulei Yang, Xiaokang Wang, Laurence T. Yang
- 年份：2023
- 出版日期：2023-10-16
- 类型：article
- 语言：en
- 来源：IEEE Network
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0890-8044
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/mnet.2023.3321923
- OpenAlex ID：https://openalex.org/W4387682186
- 落地页：https://doi.org/10.1109/mnet.2023.3321923
- 主主题：Smart Grid Security and Resilience
- 主题：Smart Grid Security and Resilience, Adversarial Robustness in Machine Learning, Network Security and Intrusion Detection
- 关键词：Computer science, Cloud computing, Cyber-physical system, Edge computing, Enhanced Data Rates for GSM Evolution, Distributed computing, Computer security, Smart grid, Secure communication, Computer network, Encryption, Telecommunications
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The rapid growth of IoT (Internet of Things) and smart services facilitate many CPS (Cyber-Physical Systems) such as smart health, smart grid and so on. Nevertheless, the communication security issues in CPS are becoming more and more important with the growing complexity of the CPS network and the increasing dependency of critical network infrastructure on cyber-based technologies. In recent years, deep learning technology has shown its superiority in detecting communication security attacks, but its high computational complexity and the massive amount of data generated by IoT devices have brought challenges to traditional cloud computing technology in terms of bandwidth and computing resources. In this paper, we have analyzed the characteristics of heterogeneity and hierarchy in attacks on CPS. We have also analyzed the role of edge intelligence in handling the security of large-scale data communication in CPS. Furthermore, we proposed a CPS communication attack detection framework based on edge cloud collaboration, aiming to improve the parallel efficiency of hardware resources when executing detection tasks. We aim to enhance the intelligence of physical devices and the degree of cloud collaboration, satisfying the real-time processing requirements of large-scale, hierarchical CPS attack detection. Furthermore, through simple simulation experiments, we verified the effectiveness of the proposed edge cloud collaboration framework in CPS attack detection.

## 16680. Common Corruption Robustness of Point Cloud Detectors: Benchmark and Enhancement

- 标题：Common Corruption Robustness of Point Cloud Detectors: Benchmark and Enhancement
- 作者：Shuangzhi Li, Zhijie Wang, Felix Juefei-Xu, Qing Guo, Xingyu Li, Lei Ma
- 年份：2023
- 出版日期：2023-10-16
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2023.3318317
- OpenAlex ID：https://openalex.org/W4387682194
- 落地页：https://doi.org/10.1109/tmm.2023.3318317
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Advanced Optical Sensing Technologies, Adversarial Robustness in Machine Learning
- 关键词：Robustness (evolution), Computer science, Point cloud, Detector, Benchmark (surveying), Cloud computing, Lidar, Data mining, Artificial intelligence, Real-time computing, Machine learning, Computer security, Remote sensing, Telecommunications
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Object detection through LiDAR-based point cloud has recently been important in autonomous driving. Although achieving high accuracy on public benchmarks, the state-of-the-art detectors may still go wrong and cause a heavy loss due to the widespread corruptions in the real world like rain, snow, sensor noise, <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">etc</i> . Nevertheless, there is a lack of a large-scale dataset covering diverse scenes and realistic corruption types with different severities to develop practical and robust point cloud detectors, which is challenging due to the heavy collection costs. To alleviate the challenge and start the first step for robust point cloud detection, we propose the physical-aware simulation methods to generate degraded point clouds under different real-world common corruptions. Then, for the first attempt, we construct a benchmark based on the physical-aware common corruptions for point cloud detectors, which contains a total of 1,122,150 examples covering 7,481 scenes, 25 common corruption types, and 6 severities. With such a novel benchmark, we conduct extensive empirical studies on 12 state-of-the-art detectors that contain 6 different detection frameworks. Thus we get several insight observations revealing the vulnerabilities of the detectors and indicating the enhancement directions. Moreover, we further study the effectiveness of existing robustness enhancement methods based on data augmentation, data denoising, test-time adaptation. The benchmark can potentially be a new platform for evaluating point cloud detectors, opening a door for developing novel robustness enhancement methods.

## 16681. Regression-Based Hyperparameter Learning for Support Vector Machines

- 标题：Regression-Based Hyperparameter Learning for Support Vector Machines
- 作者：Shili Peng, Wenwu Wang, Yinli Chen, Xueling Zhong, Qinghua Hu
- 年份：2023
- 出版日期：2023-10-17
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks and Learning Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-237X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tnnls.2023.3321685
- OpenAlex ID：https://openalex.org/W4387717516
- 落地页：https://doi.org/10.1109/tnnls.2023.3321685
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification
- 关键词：Hyperparameter, Artificial intelligence, Support vector machine, Machine learning, Hyperparameter optimization, Computer science, Regression, Margin (machine learning), Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Unification of classification and regression is a major challenge in machine learning and has attracted increasing attentions from researchers. In this article, we present a new idea for this challenge, where we convert the classification problem into a regression problem, and then use the methods in regression to solve the problem in classification. To this end, we leverage the widely used maximum margin classification algorithm and its typical representative, support vector machine (SVM). More specifically, we convert SVM into a piecewise linear regression task and propose a regression-based SVM (RBSVM) hyperparameter learning algorithm, where regression methods are used to solve several key problems in classification, such as learning of hyperparameters, calculation of prediction probabilities, and measurement of model uncertainty. To analyze the uncertainty of the model, we propose a new concept of model entropy, where the leave-one-out prediction probability of each sample is converted into entropy, and then used to quantify the uncertainty of the model. The model entropy is different from the classification margin, in the sense that it considers the distribution of all samples, not just the support vectors. Therefore, it can assess the uncertainty of the model more accurately than the classification margin. In the case of the same classification margin, the farther the sample distribution is from the classification hyperplane, the lower the model entropy. Experiments show that our algorithm (RBSVM) provides higher prediction accuracy and lower model uncertainty, when compared with state-of-the-art algorithms, such as Bayesian hyperparameter search and gradient-based hyperparameter learning algorithms.

## 16682. Explainable deep learning for attack intelligence and combating cyber–physical attacks

- 标题：Explainable deep learning for attack intelligence and combating cyber–physical attacks
- 作者：Muna Al-Hawawreh, Nour Moustafa
- 年份：2023
- 出版日期：2023-10-19
- 类型：article
- 语言：en
- 来源：Ad Hoc Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1570-8705
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.adhoc.2023.103329
- OpenAlex ID：https://openalex.org/W4387767176
- 落地页：https://doi.org/10.1016/j.adhoc.2023.103329
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Smart Grid Security and Resilience, Anomaly Detection Techniques and Applications
- 关键词：Cyber-physical system, Computer security, Process (computing), Computer science, Cyber-attack, Identification (biology), Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Cyber-physical control loops comprising sensors, actuators and controllers pose the most valued and critical part of the industrial Internet of Things (IIoT) as it regulates the state of the physical process, such as water treatment or gas flow. Thus, any malicious activities could lead to physical damage, affecting human safety. Cyber-physical attacks against the physical process are difficult to detect using existing threats and attack intelligence due to the (1) lack of such intelligence for the physical process and operational technology systems and (2) such attacks affect the process parameters and states. Artificial Intelligence (AI)-based attack intelligence is required. This study proposes an attack intelligence framework for identifying cyber–physical attacks and extracting attack intelligence. We propose an attribution module for attack identification using various machine and deep learning algorithms. We also utilize Explainable AI (XAI) to improve the explainability of the attack attribution module and extract attack intelligence. Our proposed framework is evaluated and tested using a gas pipeline dataset as a use case. We demonstrate that the proposed framework improves the understanding of attacks and provides attack rules, assisting security analysts in securing critical physical processes.

## 16683. A generalized ensemble approach based on transfer learning for Braille character recognition

- 标题：A generalized ensemble approach based on transfer learning for Braille character recognition
- 作者：Nagwa Elaraby, Sherif Barakat, Amira Rezk
- 年份：2023
- 出版日期：2023-10-23
- 类型：article
- 语言：en
- 来源：Information Processing & Management
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0306-4573
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ipm.2023.103545
- OpenAlex ID：https://openalex.org/W4387889578
- 落地页：https://doi.org/10.1016/j.ipm.2023.103545
- 主主题：Hand Gesture Recognition Systems
- 主题：Hand Gesture Recognition Systems, Tactile and Sensory Interactions, Multimodal Machine Learning Applications
- 关键词：Braille, Computer science, Benchmark (surveying), Character (mathematics), Generalization, Ensemble learning, Artificial intelligence, Transfer of learning, Speech recognition, Pattern recognition (psychology), Natural language processing, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16684. Relative Entropy Regularized Sample-Efficient Reinforcement Learning With Continuous Actions

- 标题：Relative Entropy Regularized Sample-Efficient Reinforcement Learning With Continuous Actions
- 作者：Zhiwei Shang, Renxing Li, Chunhua Zheng, Huiyun Li, Yunduan Cui
- 年份：2023
- 出版日期：2023-11-09
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks and Learning Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-237X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tnnls.2023.3329513
- OpenAlex ID：https://openalex.org/W4388543828
- 落地页：https://doi.org/10.1109/tnnls.2023.3329513
- 主主题：Reinforcement Learning in Robotics
- 主题：Reinforcement Learning in Robotics, Adaptive Dynamic Programming Control, Adversarial Robustness in Machine Learning
- 关键词：Reinforcement learning, Computer science, Regularization (linguistics), Kullback–Leibler divergence, Artificial intelligence, Softmax function, Entropy (arrow of time), Mathematical optimization, Machine learning, Mathematics, Deep learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this article, a novel reinforcement learning (RL) approach, continuous dynamic policy programming (CDPP), is proposed to tackle the issues of both learning stability and sample efficiency in the current RL methods with continuous actions. The proposed method naturally extends the relative entropy regularization from the value function-based framework to the actor-critic (AC) framework of deep deterministic policy gradient (DDPG) to stabilize the learning process in continuous action space. It tackles the intractable softmax operation over continuous actions in the critic by Monte Carlo estimation and explores the practical advantages of the Mellowmax operator. A Boltzmann sampling policy is proposed to guide the exploration of actor following the relative entropy regularized critic for superior learning capability, exploration efficiency, and robustness. Evaluated by several benchmark and real-robot-based simulation tasks, the proposed method illustrates the positive impact of the relative entropy regularization including efficient exploration behavior and stable policy update in RL with continuous action space and successfully outperforms the related baseline approaches in both sample efficiency and learning stability.

## 16685. On the Formal Evaluation of the Robustness of Neural Networks and Its Pivotal Relevance for AI-Based Safety-Critical Domains

- 标题：On the Formal Evaluation of the Robustness of Neural Networks and Its Pivotal Relevance for AI-Based Safety-Critical Domains
- 作者：Mohamed Ibn Khedher, Houda Jmila, Mounîm A. El‐Yacoubi
- 年份：2023
- 出版日期：2023-12-21
- 类型：article
- 语言：en
- 来源：International Journal of Network Dynamics and Intelligence
- 来源类型：journal
- ISSN-L：2653-6226
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.53941/ijndi.2023.100018
- OpenAlex ID：https://openalex.org/W4390110413
- 落地页：https://doi.org/10.53941/ijndi.2023.100018
- 开放 PDF 链接：https://www.sciltp.com/journals/ijndi/article/download/304/179
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning
- 关键词：Robustness (evolution), Computer science, Artificial neural network, Artificial intelligence, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Neural networks serve as a crucial role in critical tasks, where erroneous outputs can have severe consequences. Traditionally, the validation of neural networks has focused on evaluating their performance across a large set of input points to ensure desired outputs. However, due to the virtually infinite cardinality of the input space, it becomes impractical to exhaustively check all possible inputs. Networks exhibiting strong performance on extensive input samples may fail to generalize correctly in novel scenarios, and remain vulnerable to adversarial attacks. This paper presents the general pipeline of neural network robustness and provides an overview of different domains that work together to achieve robustness guarantees. These domains include evaluating the robustness against adversarial attacks, evaluating the robustness formally and applying defense techniques to enhance the robustness when the model is compromised.

## 16686. Class overlap handling methods in imbalanced domain: A comprehensive survey

- 标题：Class overlap handling methods in imbalanced domain: A comprehensive survey
- 作者：Ayyala Kishore Ajay Kumar, Dinesh Singh, Rama Shankar Yadav
- 年份：2024
- 出版日期：2024-01-11
- 类型：article
- 语言：en
- 来源：Multimedia Tools and Applications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1380-7501
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11042-023-17864-8
- OpenAlex ID：https://openalex.org/W4390741770
- 落地页：https://doi.org/10.1007/s11042-023-17864-8
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Electricity Theft Detection Techniques, Machine Learning and Data Classification
- 关键词：Overfitting, Computer science, Machine learning, Artificial intelligence, Class (philosophy), Ensemble learning, Domain (mathematical analysis), Field (mathematics), Data mining, Artificial neural network, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16687. New upper bounds for tight and fast approximation of Fisher’s exact test in dependency rule mining

- 标题：New upper bounds for tight and fast approximation of Fisher’s exact test in dependency rule mining
- 作者：Wilhelmiina Hämäläinen
- 年份：2015
- 出版日期：2015-08-11
- 类型：article
- 语言：en
- 来源：Computational Statistics & Data Analysis
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-9473
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.csda.2015.08.002
- OpenAlex ID：https://openalex.org/W1160788859
- 落地页：https://doi.org/10.1016/j.csda.2015.08.002
- 主主题：Data Mining Algorithms and Applications
- 主题：Data Mining Algorithms and Applications, Data Quality and Management, Machine Learning and Data Classification
- 关键词：Mathematics, Pruning, Dependency (UML), Spurious relationship, Measure (data warehouse), Upper and lower bounds, Exact test, Contingency table, Statistical hypothesis testing, Constant (computer programming), Algorithm, Mathematical optimization, Applied mathematics, Computer science, Statistics, Data mining, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16688. A framework for automatic semantic video annotation

- 标题：A framework for automatic semantic video annotation
- 作者：Amjad Altadmri, Amr Ahmed
- 年份：2013
- 出版日期：2013-03-27
- 类型：article
- 语言：en
- 来源：Multimedia Tools and Applications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1380-7501
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1007/s11042-013-1363-6
- OpenAlex ID：https://openalex.org/W1522688615
- 落地页：https://doi.org/10.1007/s11042-013-1363-6
- 主主题：Video Analysis and Summarization
- 主题：Video Analysis and Summarization, Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications
- 关键词：Computer science, Annotation, Information retrieval, Search engine indexing, Semantics (computer science), Image retrieval, Semantic gap, Matching (statistics), Ontology, Semantic similarity, Similarity (geometry), Artificial intelligence, Natural language processing, Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16689. A Robust Class of Data Languages and an Application to Learning

- 标题：A Robust Class of Data Languages and an Application to Learning
- 作者：Benedikt Bollig, Peter Habermehl, Martin Leucker, Benjamin Monmege
- 年份：2014
- 出版日期：2014-12-30
- 类型：article
- 语言：en
- 来源：Logical Methods in Computer Science
- 来源类型：journal
- 出版方：Logical Methods in Computer Science e.V.
- ISSN-L：1860-5974
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.2168/lmcs-10(4:19)2014
- OpenAlex ID：https://openalex.org/W1793241515
- 落地页：https://doi.org/10.2168/lmcs-10(4:19)2014
- 开放 PDF 链接：https://lmcs.episciences.org/1030/pdf
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, semigroups and automata theory, Software Testing and Debugging Techniques
- 关键词：Computer science, Nested word, Theoretical computer science, Decidability, Automaton, Quantum finite automata, Session (web analytics), Automata theory
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We introduce session automata, an automata model to process data words, i.e., words over an infinite alphabet. Session automata support the notion of fresh data values, which are well suited for modeling protocols in which sessions using fresh values are of major interest, like in security protocols or ad-hoc networks. Session automata have an expressiveness partly extending, partly reducing that of classical register automata. We show that, unlike register automata and their various extensions, session automata are robust: They (i) are closed under intersection, union, and (resource-sensitive) complementation, (ii) admit a symbolic regular representation, (iii) have a decidable inclusion problem (unlike register automata), and (iv) enjoy logical characterizations. Using these results, we establish a learning algorithm to infer session automata through membership and equivalence queries.

## 16690. <b>rFerns</b>: An Implementation of the Random Ferns Method for General-Purpose Machine Learning

- 标题：<b>rFerns</b>: An Implementation of the Random Ferns Method for General-Purpose Machine Learning
- 作者：Miron B. Kursa
- 年份：2014
- 出版日期：2014-01-01
- 类型：article
- 语言：en
- 来源：Journal of Statistical Software
- 来源类型：journal
- 出版方：Foundation for Open Access Statistics
- ISSN-L：1548-7660
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.18637/jss.v061.i10
- OpenAlex ID：https://openalex.org/W1829981714
- 落地页：https://doi.org/10.18637/jss.v061.i10
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Advanced Image and Video Retrieval Techniques, Algorithms and Data Compression
- 关键词：Computer science, Random forest, Simple (philosophy), Decision tree, Artificial intelligence, Measure (data warehouse), Machine learning, Tree (set theory), Interpretation (philosophy), Random tree, Algorithm, Theoretical computer science, Data mining, Mathematics, Combinatorics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Random ferns is a very simple yet powerful classification method originally introduced for specific computer vision tasks. In this paper, I show that this algorithm may be considered as a constrained decision tree ensemble and use this interpretation to introduce a series of modifications which enable the use of random ferns in general machine learning problems. Moreover, I extend the method with an internal error approximation and an attribute importance measure based on corresponding features of the random forest algorithm. I also present the R package rFerns containing an efficient implementation of this modified version of random ferns.

## 16691. Immunity and pseudorandomness of context-free languages

- 标题：Immunity and pseudorandomness of context-free languages
- 作者：Tomoyuki Yamakami
- 年份：2011
- 出版日期：2011-08-02
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.tcs.2011.07.013
- OpenAlex ID：https://openalex.org/W1849715658
- 落地页：https://doi.org/10.1016/j.tcs.2011.07.013
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Coding theory and cryptography, Machine Learning and Algorithms
- 关键词：Context-free language, Regular language, Pseudorandomness, Discrete mathematics, Context (archaeology), Computer science, Mathematics, Pseudorandom number generator, Combinatorics, Theoretical computer science, Algorithm, Automaton, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16692. RECOVERING THE BASIC STRUCTURE OF HUMAN ACTIVITIES FROM NOISY VIDEO-BASED SYMBOL STRINGS

- 标题：RECOVERING THE BASIC STRUCTURE OF HUMAN ACTIVITIES FROM NOISY VIDEO-BASED SYMBOL STRINGS
- 作者：Kris Kitani, Yoichi Sato, Akihiro Sugimoto
- 年份：2008
- 出版日期：2008-12-01
- 类型：article
- 语言：en
- 来源：International Journal of Pattern Recognition and Artificial Intelligence
- 来源类型：journal
- 出版方：World Scientific
- ISSN-L：0218-0014
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1142/s0218001408006776
- OpenAlex ID：https://openalex.org/W1964583714
- 落地页：https://doi.org/10.1142/s0218001408006776
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Video Analysis and Summarization, Multimodal Machine Learning Applications
- 关键词：Computer science, Robustness (evolution), Artificial intelligence, Rule-based machine translation, Noise (video), Symbol (formal), Data compression, Machine learning, Pattern recognition (psychology), Theoretical computer science, Speech recognition, Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In recent years stochastic context-free grammars have been shown to be effective in modeling human activities because of the hierarchical structures they represent. However, most of the research in this area has yet to address the issue of learning the activity grammars from a noisy input source, namely, video. In this paper, we present a framework for identifying noise and recovering the basic activity grammar from a noisy symbol string produced by video. We identify the noise symbols by finding the set of non-noise symbols that optimally compresses the training data, where the optimality of compression is measured using an MDL criterion. We show the robustness of our system to noise and its effectiveness in learning the basic structure of human activity, through experiments with artificial data and a real video sequence from a local convenience store.

## 16693. Benchmarking local classification methods

- 标题：Benchmarking local classification methods
- 作者：Bernd Bischl, Julia Schiffner, Claus Weihs
- 年份：2013
- 出版日期：2013-05-07
- 类型：article
- 语言：en
- 来源：Computational Statistics
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0943-4062
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00180-013-0420-y
- OpenAlex ID：https://openalex.org/W1967004441
- 落地页：https://doi.org/10.1007/s00180-013-0420-y
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Neural Networks and Applications, Machine Learning and Data Classification
- 关键词：Benchmarking, Benchmark (surveying), Computer science, Machine learning, Artificial intelligence, Term (time), Data mining, Geography
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16694. Efficient Analysis of Probabilistic Programs with an Unbounded Counter

- 标题：Efficient Analysis of Probabilistic Programs with an Unbounded Counter
- 作者：Tomǎš Brázdil, Stefan Kiefer, Antonı́n Kučera
- 年份：2014
- 出版日期：2014-12-17
- 类型：article
- 语言：en
- 来源：Journal of the ACM
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：0004-5411
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/2629599
- OpenAlex ID：https://openalex.org/W1975636681
- 落地页：https://doi.org/10.1145/2629599
- 主主题：Formal Methods in Verification
- 主题：Formal Methods in Verification, Logic, Reasoning, and Knowledge, Machine Learning and Algorithms
- 关键词：Probabilistic logic, Probabilistic automaton, Mathematics, Martingale (probability theory), Probabilistic analysis of algorithms, Automaton, Discrete mathematics, Property (philosophy), Divergence (linguistics), Counterexample, Computer science, Algorithm, Theoretical computer science, Applied mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We show that a subclass of infinite-state probabilistic programs that can be modeled by probabilistic one-counter automata (pOC) admits an efficient quantitative analysis. We start by establishing a powerful link between pOC and martingale theory, which leads to fundamental observations about quantitative properties of runs in pOC. In particular, we provide a “divergence gap theorem”, which bounds a positive non-termination probability in pOC away from zero. Using these observations, we show that the expected termination time can be approximated up to an arbitrarily small relative error in polynomial time, and the same holds for the probability of all runs that satisfy a given ω-regular property encoded by a deterministic Rabin automaton.

## 16695. Improved sparse fourier approximation results: faster implementations and stronger guarantees

- 标题：Improved sparse fourier approximation results: faster implementations and stronger guarantees
- 作者：Ben Segal, Mark Iwen
- 年份：2012
- 出版日期：2012-07-25
- 类型：article
- 语言：en
- 来源：Numerical Algorithms
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1017-1398
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11075-012-9621-7
- OpenAlex ID：https://openalex.org/W1977453732
- 落地页：https://doi.org/10.1007/s11075-012-9621-7
- 主主题：Sparse and Compressive Sensing Techniques
- 主题：Sparse and Compressive Sensing Techniques, Mathematical Approximation and Integration, Machine Learning and Algorithms
- 关键词：Fourier transform, Mathematics, Sublinear function, Fourier series, Fourier inversion theorem, Fourier analysis, Fast Fourier transform, Applied mathematics, Algorithm, Discrete mathematics, Mathematical analysis, Short-time Fourier transform
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16696. Limits to measurement in experiments governed by algorithms

- 标题：Limits to measurement in experiments governed by algorithms
- 作者：Edwin Beggs, José Félix Costa, John V. Tucker
- 年份：2010
- 出版日期：2010-11-08
- 类型：article
- 语言：en
- 来源：Mathematical Structures in Computer Science
- 来源类型：journal
- 出版方：Cambridge University Press
- ISSN-L：0960-1295
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1017/s0960129510000356
- OpenAlex ID：https://openalex.org/W1981161833
- 落地页：https://doi.org/10.1017/s0960129510000356
- 主主题：Computability, Logic, AI Algorithms
- 主题：Computability, Logic, AI Algorithms, Machine Learning and Algorithms, Evolutionary Algorithms and Applications
- 关键词：Oracle, Computer science, Physical system, Super-recursive algorithm, Turing machine, Limit (mathematics), Turing, Algorithm, Theoretical computer science, Computation, Simple (philosophy), Mathematics, Universal Turing machine, Physics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We pose the following question: If a physical experiment were to be completely controlled by an algorithm, what effect would the algorithm have on the physical measurements made possible by the experiment ? In a programme to study the nature of computation possible by physical systems, and by algorithms coupled with physical systems, we have begun to analyse: (i) the algorithmic nature of experimental procedures; and (ii) the idea of using a physical experiment as an oracle to Turing Machines. To answer the question, we will extend our theory of experimental oracles so that we can use Turing machines to model the experimental procedures that govern the conduct of physical experiments. First, we specify an experiment that measures mass via collisions in Newtonian dynamics and examine its properties in preparation for its use as an oracle. We begin the classification of the computational power of polynomial time Turing machines with this experimental oracle using non-uniform complexity classes. Second, we show that modelling an experimenter and experimental procedure algorithmically imposes a limit on what can be measured using equipment. Indeed, the theorems suggest a new form of uncertainty principle for our knowledge of physical quantities measured in simple physical experiments. We argue that the results established here are representative of a huge class of experiments.

## 16697. An ensemble approach of dual base learners for multi-class classification problems

- 标题：An ensemble approach of dual base learners for multi-class classification problems
- 作者：M. Paz Sesmero, Juan M. Alonso-Weber, Germán Gutiérrez, Agapito Ledezma, Araceli Sanchis
- 年份：2014
- 出版日期：2014-09-22
- 类型：article
- 语言：en
- 来源：Information Fusion
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1566-2535
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1016/j.inffus.2014.09.002
- OpenAlex ID：https://openalex.org/W1982235653
- 落地页：https://doi.org/10.1016/j.inffus.2014.09.002
- 开放 PDF 链接：https://www.sciencedirect.com/science/article/pii/S156625351400102X
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Machine Learning and Data Classification, Face and Expression Recognition
- 关键词：Computer science, Pairwise comparison, Class (philosophy), Ensemble learning, Machine learning, Artificial intelligence, Base (topology), Binary number, Dual (grammatical number), Binary classification, Decomposition, Quality (philosophy), Data mining, Support vector machine, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16698. k-<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" altimg="si1.gif" overflow="scroll"><mml:mrow><mml:mi mathvariant="normal">Means</mml:mi></mml:mrow><mml:mo>+</mml:mo><mml:mo>+</mml:mo></mml:math> under approximation stability

- 标题：k-<mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML" altimg="si1.gif" overflow="scroll"><mml:mrow><mml:mi mathvariant="normal">Means</mml:mi></mml:mrow><mml:mo>+</mml:mo><mml:mo>+</mml:mo></mml:math> under approximation stability
- 作者：Manu Agarwal, Ragesh Jaiswal, Arindam Pal
- 年份：2015
- 出版日期：2015-05-02
- 类型：article
- 语言：lv
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.tcs.2015.04.030
- OpenAlex ID：https://openalex.org/W1990772655
- 落地页：https://doi.org/10.1016/j.tcs.2015.04.030
- 主主题：Data Management and Algorithms
- 主题：Data Management and Algorithms, Complexity and Algorithms in Graphs, Machine Learning and Algorithms
- 关键词：Algorithm, Mathematics, Initialization, Combinatorics, Constant (computer programming), Heuristic, Center (category theory), Discrete mathematics, Computer science, Mathematical optimization
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16699. Learnability and Definability in Trees and Similar Structures

- 标题：Learnability and Definability in Trees and Similar Structures
- 作者：Martin Grohe, Gy. Tur�n
- 年份：2003
- 出版日期：2003-12-23
- 类型：article
- 语言：en
- 来源：Theory of Computing Systems
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1432-4350
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00224-003-1112-8
- OpenAlex ID：https://openalex.org/W1996805091
- 落地页：https://doi.org/10.1007/s00224-003-1112-8
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Complexity and Algorithms in Graphs, Optimization and Search Problems
- 关键词：Learnability, Bounded function, Mathematics, VC dimension, Discrete mathematics, Combinatorics, Clique, Dimension (graph theory), Mathematical proof, Treewidth, Set (abstract data type), Computer science, Graph, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16700. Simultaneous feature and parameter selection using multiobjective optimization: application to named entity recognition

- 标题：Simultaneous feature and parameter selection using multiobjective optimization: application to named entity recognition
- 作者：Asif Ekbal, Sriparna Saha
- 年份：2014
- 出版日期：2014-07-05
- 类型：article
- 语言：en
- 来源：International Journal of Machine Learning and Cybernetics
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1868-8071
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s13042-014-0268-7
- OpenAlex ID：https://openalex.org/W2002484979
- 落地页：https://doi.org/10.1007/s13042-014-0268-7
- 主主题：Text and Document Classification Technologies
- 主题：Text and Document Classification Technologies, Machine Learning and Data Classification, Topic Modeling
- 关键词：Feature selection, Artificial intelligence, Computer science, Pattern recognition (psychology), Classifier (UML), Bengali, Conditional random field, Multi-objective optimization, Telugu, Support vector machine, Feature (linguistics), Optimization problem, Machine learning, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16701. Structural and textural classification of erythrocytes in anaemic cases: A scanning electron microscopic study

- 标题：Structural and textural classification of erythrocytes in anaemic cases: A scanning electron microscopic study
- 作者：Sirsendu Bhowmick, Dev Kumar Das, Asok Kumar Maiti, Chandan Chakraborty
- 年份：2012
- 出版日期：2012-09-26
- 类型：article
- 语言：en
- 来源：Micron
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0968-4328
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.micron.2012.09.003
- OpenAlex ID：https://openalex.org/W2003577784
- 落地页：https://doi.org/10.1016/j.micron.2012.09.003
- 主主题：Digital Imaging for Blood Diseases
- 主题：Digital Imaging for Blood Diseases, Blood properties and coagulation, Machine Learning and Data Classification
- 关键词：Scanning electron microscope, Pattern recognition (psychology), Artificial intelligence, Pathology, Computer science, Materials science, Medicine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16702. Mandatory Leaf Node Prediction in Hierarchical Multilabel Classification

- 标题：Mandatory Leaf Node Prediction in Hierarchical Multilabel Classification
- 作者：Wei Bi, James T. Kwok
- 年份：2014
- 出版日期：2014-05-06
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks and Learning Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-237X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tnnls.2014.2309437
- OpenAlex ID：https://openalex.org/W2007098590
- 落地页：https://doi.org/10.1109/tnnls.2014.2309437
- 主主题：Text and Document Classification Technologies
- 主题：Text and Document Classification Technologies, Algorithms and Data Compression, Machine Learning and Data Classification
- 关键词：Hierarchy, Directed acyclic graph, Computer science, Multi-label classification, Tree (set theory), Multiclass classification, Node (physics), Graph, Artificial intelligence, Machine learning, Pattern recognition (psychology), Data mining, Theoretical computer science, Algorithm, Mathematics, Support vector machine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In hierarchical classification, the output labels reside on a tree- or directed acyclic graph (DAG)-structured hierarchy. On testing, the prediction paths of a given test example may be required to end at leaf nodes of the label hierarchy. This is called mandatory leaf node prediction (MLNP) and is particularly useful, when the leaf nodes have much stronger semantic meaning than the internal nodes. However, while there have been a lot of MLNP methods in hierarchical multiclass classification, performing MLNP in hierarchical multilabel classification is difficult. In this paper, we propose novel MLNP algorithms that consider the global label hierarchy structure. We show that the joint posterior probability over all the node labels can be efficiently maximized by dynamic programming for label trees, or greedy algorithm for label DAGs. In addition, both algorithms can be further extended for the minimization of the expected symmetric loss. Experiments are performed on real-world MLNP data sets with label trees and label DAGs. The proposed method consistently outperforms other hierarchical and flat multilabel classification methods.

## 16703. Pattern matching with variables: A multivariate complexity analysis

- 标题：Pattern matching with variables: A multivariate complexity analysis
- 作者：Henning Fernau, Markus L. Schmid
- 年份：2015
- 出版日期：2015-04-06
- 类型：article
- 语言：en
- 来源：Information and Computation
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0890-5401
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ic.2015.03.006
- OpenAlex ID：https://openalex.org/W2007197043
- 落地页：https://doi.org/10.1016/j.ic.2015.03.006
- 主主题：Algorithms and Data Compression
- 主题：Algorithms and Data Compression, semigroups and automata theory, Machine Learning and Algorithms
- 关键词：Mathematics, Cardinality (data modeling), Word (group theory), Terminal (telecommunication), Combinatorics, String (physics), Injective function, Bounded function, Variable (mathematics), Alphabet, Matching (statistics), Discrete mathematics, Statistics, Computer science, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16704. Test generation from P systems using model checking

- 标题：Test generation from P systems using model checking
- 作者：Florentin Ipate, Marian Gheorghe, Raluca Lefticaru
- 年份：2010
- 出版日期：2010-04-03
- 类型：article
- 语言：en
- 来源：The Journal of Logic and Algebraic Programming
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1567-8326
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.jlap.2010.03.007
- OpenAlex ID：https://openalex.org/W2011118910
- 落地页：https://doi.org/10.1016/j.jlap.2010.03.007
- 主主题：DNA and Biological Computing
- 主题：DNA and Biological Computing, Software Testing and Debugging Techniques, Machine Learning and Algorithms
- 关键词：Kripke structure, Model checking, Counterexample, Algorithm, Set (abstract data type), Context (archaeology), Linear temporal logic, Mathematics, Simple (philosophy), Computer science, Theoretical computer science, Discrete mathematics, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16705. A novel method for constructing ensemble classifiers

- 标题：A novel method for constructing ensemble classifiers
- 作者：Chunxia Zhang, Jiangshe Zhang
- 年份：2008
- 出版日期：2008-09-06
- 类型：article
- 语言：en
- 来源：Statistics and Computing
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0960-3174
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11222-008-9094-7
- OpenAlex ID：https://openalex.org/W2015916203
- 落地页：https://doi.org/10.1007/s11222-008-9094-7
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Neural Networks and Applications, Machine Learning and Data Classification
- 关键词：Random subspace method, Artificial intelligence, Computer science, Machine learning, Pattern recognition (psychology), Mathematics, Classifier (UML)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16706. Storage capacity of the fully-connected committee machine

- 标题：Storage capacity of the fully-connected committee machine
- 作者：Robert Urbanczik
- 年份：1997
- 出版日期：1997-06-07
- 类型：article
- 语言：en
- 来源：Journal of Physics A Mathematical and General
- 来源类型：journal
- 出版方：Institute of Physics
- ISSN-L：0305-4470
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1088/0305-4470/30/11/007
- OpenAlex ID：https://openalex.org/W2024367258
- 落地页：https://doi.org/10.1088/0305-4470/30/11/007
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Computability, Logic, AI Algorithms, Cellular Automata and Applications
- 关键词：Entropy (arrow of time), Computer science, Mathematics, Physics, Thermodynamics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The storage capacity, that is the number of patterns which can be stored per weight, is calculated for the fully-connected committee machine with real couplings and K hidden units from the vanishing of the entropy of the internal representations, and it is found to diverge as .

## 16707. The Logic Of Reliable And Efficient Inquiry

- 标题：The Logic Of Reliable And Efficient Inquiry
- 作者：Oliver Schulte
- 年份：1999
- 出版日期：1999-08-01
- 类型：article
- 语言：en
- 来源：Journal of Philosophical Logic
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0022-3611
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1023/a:1004443206028
- OpenAlex ID：https://openalex.org/W2024726681
- 落地页：https://doi.org/10.1023/a:1004443206028
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, Computability, Logic, AI Algorithms
- 关键词：Instrumentalism, Convergence (economics), Inductive reasoning, Inference, Computer science, Theory, Set (abstract data type), Epistemology, Artificial intelligence, Mathematical economics, Calculus (dental), Mathematics, Philosophy
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16708. On Bayesian Network Classifiers with Reduced Precision Parameters

- 标题：On Bayesian Network Classifiers with Reduced Precision Parameters
- 作者：Sebastian Tschiatschek, Franz Pernkopf
- 年份：2014
- 出版日期：2014-08-29
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Pattern Analysis and Machine Intelligence
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：0162-8828
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tpami.2014.2353620
- OpenAlex ID：https://openalex.org/W2028980143
- 落地页：https://doi.org/10.1109/tpami.2014.2353620
- 主主题：Bayesian Modeling and Causal Inference
- 主题：Bayesian Modeling and Causal Inference, Machine Learning and Data Classification, Fault Detection and Control Systems
- 关键词：Computer science, Robustness (evolution), Quantization (signal processing), Naive Bayes classifier, Benchmark (surveying), Artificial intelligence, Classifier (UML), Decision tree, Bayesian network, Machine learning, Implementation, Algorithm, Pattern recognition (psychology), Data mining, Support vector machine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Bayesian network classifier (BNCs) are typically implemented on nowadays desktop computers. However, many real world applications require classifier implementation on embedded or low power systems. Aspects for this purpose have not been studied rigorously. We partly close this gap by analyzing reduced precision implementations of BNCs. In detail, we investigate the quantization of the parameters of BNCs with discrete valued nodes including the implications on the classification rate (CR). We derive worst-case and probabilistic bounds on the CR for different bit-widths. These bounds are evaluated on several benchmark datasets. Furthermore, we compare the classification performance and the robustness of BNCs with generatively and discriminatively optimized parameters, i.e. parameters optimized for high data likelihood and parameters optimized for classification, with respect to parameter quantization. Generatively optimized parameters are more robust for very low bit-widths, i.e. less classifications change because of quantization. However, classification performance is better for discriminatively optimized parameters for all but very low bit-widths. Additionally, we perform analysis for margin-optimized tree augmented network (TAN) structures which outperform generatively optimized TAN structures in terms of CR and robustness.

## 16709. ROCS: Receiver Operating Characteristic Surface for Class-Skewed High-Throughput Data

- 标题：ROCS: Receiver Operating Characteristic Surface for Class-Skewed High-Throughput Data
- 作者：Tianwei Yu
- 年份：2012
- 出版日期：2012-07-06
- 类型：article
- 语言：en
- 来源：PLoS ONE
- 来源类型：journal
- 出版方：Public Library of Science
- ISSN-L：1932-6203
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1371/journal.pone.0040598
- OpenAlex ID：https://openalex.org/W2033498061
- 落地页：https://doi.org/10.1371/journal.pone.0040598
- 开放 PDF 链接：https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0040598&type=printable
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Machine Learning and Data Classification, Digital Imaging for Blood Diseases
- 关键词：Receiver operating characteristic, Classifier (UML), Area under curve, False positive rate, Computer science, Throughput, Artificial intelligence, Area under the curve, Pattern recognition (psychology), Statistics, Mathematics, Data mining, Biology, Bioinformatics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The receiver operating characteristic (ROC) curve is an important tool to gauge the performance of classifiers. In certain situations of high-throughput data analysis, the data is heavily class-skewed, i.e. most features tested belong to the true negative class. In such cases, only a small portion of the ROC curve is relevant in practical terms, rendering the ROC curve and its area under the curve (AUC) insufficient for the purpose of judging classifier performance. Here we define an ROC surface (ROCS) using true positive rate (TPR), false positive rate (FPR), and true discovery rate (TDR). The ROC surface, together with the associated quantities, volume under the surface (VUS) and FDR-controlled area under the ROC curve (FCAUC), provide a useful approach for gauging classifier performance on class-skewed high-throughput data. The implementation as an R package is available at http://userwww.service.emory.edu/~tyu8/ROCS/.

## 16710. Reusable components in decision tree induction algorithms

- 标题：Reusable components in decision tree induction algorithms
- 作者：Milija Suknović, Boris Delibašić, Miloš Jovanović, Milan Vukičević, Dragana Bečejski-Vujaklija, Zoran Obradović
- 年份：2011
- 出版日期：2011-02-16
- 类型：article
- 语言：en
- 来源：Computational Statistics
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0943-4062
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00180-011-0242-8
- OpenAlex ID：https://openalex.org/W2041781402
- 落地页：https://doi.org/10.1007/s00180-011-0242-8
- 主主题：Data Mining Algorithms and Applications
- 主题：Data Mining Algorithms and Applications, Rough Sets and Fuzzy Logic, Machine Learning and Data Classification
- 关键词：Computer science, Decision tree, Component (thermodynamics), ID3 algorithm, Algorithm, Incremental decision tree, Tree (set theory), Decision tree learning, Data mining, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16711. A new classifier based on information theoretic learning with unlabeled data

- 标题：A new classifier based on information theoretic learning with unlabeled data
- 作者：Kyu-Hwa Jeong, Jian‐Wu Xu, Deniz Erdoğmuş, José C. Prı́ncipe
- 年份：2005
- 出版日期：2005-07-01
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neunet.2005.06.018
- OpenAlex ID：https://openalex.org/W2049952536
- 落地页：https://doi.org/10.1016/j.neunet.2005.06.018
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Blind Source Separation Techniques, Machine Learning and Algorithms
- 关键词：Computer science, Machine learning, Artificial intelligence, Semi-supervised learning, Boosting (machine learning), Classifier (UML), Labeled data, Pairwise comparison, Minification, Pattern recognition (psychology), Training set
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16712. On the robustness of a one-period look-ahead policy in multi-armed bandit problems

- 标题：On the robustness of a one-period look-ahead policy in multi-armed bandit problems
- 作者：Ilya O. Ryzhov, Peter I. Frazier, Warren B. Powell
- 年份：2010
- 出版日期：2010-05-01
- 类型：article
- 语言：en
- 来源：Procedia Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1877-0509
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1016/j.procs.2010.04.183
- OpenAlex ID：https://openalex.org/W2054387444
- 落地页：https://doi.org/10.1016/j.procs.2010.04.183
- 主主题：Advanced Bandit Algorithms Research
- 主题：Advanced Bandit Algorithms Research, Machine Learning and Algorithms, Reinforcement Learning in Robotics
- 关键词：Robustness (evolution), Heuristics, Computer science, Mathematical optimization, Multi-armed bandit, Operations research, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We analyze the robustness of a knowledge gradient (KG) policy for the multi-armed bandit problem. The KG policy is based on a one-period look-ahead, which is known to underperform in other learning problems when the marginal value of information is non-concave. We present an adjustment that corrects for non-concavity and approximates a multi-step look-ahead, and compare its performance to the unadjusted KG policy and other heuristics. We provide guidance for determining when adjustment will improve performance, and when it is unnecessary. We present evidence suggesting that KG is generally robust in the multi-armed bandit setting, which argues in favour of KG as an alternative to index policies.

## 16713. Latent semantic learning with structured sparse representation for human action recognition

- 标题：Latent semantic learning with structured sparse representation for human action recognition
- 作者：Zhiwu Lu, Yuxin Peng
- 年份：2012
- 出版日期：2012-10-11
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.patcog.2012.09.027
- OpenAlex ID：https://openalex.org/W2061017033
- 落地页：https://doi.org/10.1016/j.patcog.2012.09.027
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Gait Recognition and Analysis, Multimodal Machine Learning Applications
- 关键词：Probabilistic latent semantic analysis, Computer science, Artificial intelligence, Embedding, Pattern recognition (psychology), Discriminative model, Graph, Latent semantic analysis, Feature learning, Sparse approximation, Machine learning, Semantics (computer science), Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16714. An alternating hierarchy for finite automata

- 标题：An alternating hierarchy for finite automata
- 作者：Viliam Geffert
- 年份：2012
- 出版日期：2012-05-05
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.tcs.2012.04.044
- OpenAlex ID：https://openalex.org/W2061996338
- 落地页：https://doi.org/10.1016/j.tcs.2012.04.044
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Machine Learning and Algorithms, Chemical Synthesis and Analysis
- 关键词：Mathematics, Bounded function, Discrete mathematics, Combinatorics, Deterministic finite automaton, Quantum finite automata, ω-automaton, Hierarchy, Deterministic automaton, Intersection (aeronautics), Finite-state machine, Nondeterministic finite automaton, Automaton, Automata theory, Computer science, Algorithm, Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16715. Estimation of the Rate–Distortion Function

- 标题：Estimation of the Rate–Distortion Function
- 作者：Matthew Tom Harrison, Ioannis Kontoyiannis
- 年份：2008
- 出版日期：2008-07-24
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tit.2008.926387
- OpenAlex ID：https://openalex.org/W2063299195
- 落地页：https://doi.org/10.1109/tit.2008.926387
- 主主题：Wireless Communication Security Techniques
- 主题：Wireless Communication Security Techniques, Algorithms and Data Compression, Machine Learning and Algorithms
- 关键词：Estimator, Mathematics, Lossy compression, Consistency (knowledge bases), Applied mathematics, Distortion (music), Mathematical optimization, Rate–distortion theory, Algorithm, Statistics, Computer science, Data compression, Discrete mathematics, Bandwidth (computing)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
<para xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> Motivated by questions in lossy data compression and by theoretical considerations, the problem of estimating the rate–distortion function of an unknown (not necessarily discrete-valued) source from empirical data is examined. The focus is the behavior of the so-called “plug-in” estimator, which is simply the rate–distortion function of the empirical distribution of the observed data. Sufficient conditions are given for its consistency, and examples are provided demonstrating that in certain cases it fails to converge to the true rate–distortion function. The analysis of its performance is complicated by the fact that the rate–distortion function is not continuous in the source distribution; the underlying mathematical problem is closely related to the classical problem of establishing the consistency of maximum-likelihood estimators (MLEs). General consistency results are given for the plug-in estimator applied to a broad class of sources, including all stationary and ergodic ones. A more general class of estimation problems is also considered, arising in the context of lossy data compression when the allowed class of coding distributions is restricted; analogous results are developed for the plug-in estimator in that case. Finally, consistency theorems are formulated for modified (e.g., penalized) versions of the plug-in, and for estimating the optimal reproduction distribution. </para>

## 16716. An application of a new meta-heuristic for optimizing the classification accuracy when analyzing some medical datasets

- 标题：An application of a new meta-heuristic for optimizing the classification accuracy when analyzing some medical datasets
- 作者：Huy Pham, Evangelos Triantaphyllou
- 年份：2008
- 出版日期：2008-12-25
- 类型：article
- 语言：en
- 来源：Expert Systems with Applications
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0957-4174
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.eswa.2008.12.007
- OpenAlex ID：https://openalex.org/W2077792286
- 落地页：https://doi.org/10.1016/j.eswa.2008.12.007
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Artificial Intelligence in Healthcare, Imbalanced Data Classification Techniques
- 关键词：Computer science, Heuristic, Meta heuristic, Artificial intelligence, Machine learning, Data mining, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16717. Learning Causal Structure from Multiple Datasets with Similar Variable Sets

- 标题：Learning Causal Structure from Multiple Datasets with Similar Variable Sets
- 作者：Robert E. Tillman, Frederick Eberhardt
- 年份：2014
- 出版日期：2014-01-01
- 类型：article
- 语言：en
- 来源：Behaviormetrika
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0385-7417
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.2333/bhmk.41.41
- OpenAlex ID：https://openalex.org/W2086604640
- 落地页：https://doi.org/10.2333/bhmk.41.41
- 主主题：Bayesian Modeling and Causal Inference
- 主题：Bayesian Modeling and Causal Inference, Machine Learning and Data Classification, Multi-Criteria Decision Making
- 关键词：Conditional independence, Set (abstract data type), Variable (mathematics), Independence (probability theory), Computer science, Causal structure, Causal inference, Measure (data warehouse), Observational study, Causal model, Econometrics, Variables, Machine learning, Data mining, Artificial intelligence, Statistics, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16718. Cost-sensitive selective naive Bayes classifiers for predicting the increase of the h-index for scientific journals

- 标题：Cost-sensitive selective naive Bayes classifiers for predicting the increase of the h-index for scientific journals
- 作者：Alfonso Ibáñez, Concha Bielza, Pedro Larrañaga
- 年份：2014
- 出版日期：2014-01-04
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2013.08.042
- OpenAlex ID：https://openalex.org/W2091425332
- 落地页：https://doi.org/10.1016/j.neucom.2013.08.042
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Explainable Artificial Intelligence (XAI), Machine Learning and Data Classification
- 关键词：Naive Bayes classifier, Computer science, Machine learning, Artificial intelligence, Bayes' theorem, Class (philosophy), Index (typography), Bayesian probability, Variable (mathematics), Data mining, Mathematics, Support vector machine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16719. A hybridized tabu search approach for the minimum weight vertex cover problem

- 标题：A hybridized tabu search approach for the minimum weight vertex cover problem
- 作者：Stefan Voß, Andréas Fink
- 年份：2012
- 出版日期：2012-09-18
- 类型：article
- 语言：en
- 来源：Journal of Heuristics
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1381-1231
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10732-012-9211-9
- OpenAlex ID：https://openalex.org/W2092783294
- 落地页：https://doi.org/10.1007/s10732-012-9211-9
- 主主题：Complexity and Algorithms in Graphs
- 主题：Complexity and Algorithms in Graphs, Optimization and Search Problems, Machine Learning and Algorithms
- 关键词：Tabu search, Metaheuristic, Simulated annealing, Mathematics, Vertex (graph theory), Vertex cover, Minimum weight, Combinatorics, Edge cover, Combinatorial optimization, Mathematical optimization, Random walk, Local search (optimization), Graph
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16720. The Research of Data Mining Based on Neural Networks

- 标题：The Research of Data Mining Based on Neural Networks
- 作者：Qiong Guo, Jing Niu
- 年份：2014
- 出版日期：2014-07-01
- 类型：article
- 语言：en
- 来源：Advanced materials research
- 来源类型：journal
- 出版方：Trans Tech Publications
- ISSN-L：1022-6680
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.4028/www.scientific.net/amr.989-994.2080
- OpenAlex ID：https://openalex.org/W2107906369
- 落地页：https://doi.org/10.4028/www.scientific.net/amr.989-994.2080
- 主主题：Rough Sets and Fuzzy Logic
- 主题：Rough Sets and Fuzzy Logic, Neural Networks and Applications, Machine Learning and Algorithms
- 关键词：Artificial neural network, Computer science, Field (mathematics), Process (computing), Artificial intelligence, Data processing, Data mining, Nervous system network models, Information processing, Machine learning, Time delay neural network, Types of artificial neural networks, Database
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Artificial neural network is a kind of network system that simulating human brain information processing mechanism developed on the basis of modern neurobiology research. It not only has the ability to deal with general calculation of numerical data, but also has the thinking for processing knowledge and memory ability of learning. Data mining process based on neural network consists of data preparation, rules extraction and evaluation. In this paper, the research status of data mining, neural network, development trend and application field are reviewed and this paper expounds the basic concepts of data mining, neural network, the basic model and the traditional implementation method.

## 16721. On universal transfer learning

- 标题：On universal transfer learning
- 作者：Maqsood Mahmud
- 年份：2009
- 出版日期：2009-02-01
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.tcs.2009.01.013
- OpenAlex ID：https://openalex.org/W2108723060
- 落地页：https://doi.org/10.1016/j.tcs.2009.01.013
- 主主题：Computability, Logic, AI Algorithms
- 主题：Computability, Logic, AI Algorithms, Machine Learning and Algorithms, Statistical Mechanics and Entropy
- 关键词：Transfer of learning, Computer science, Inductive transfer, Inductive reasoning, Inference, Kolmogorov complexity, Algorithmic learning theory, Perspective (graphical), Context (archaeology), Learning theory, Artificial intelligence, Information theory, Bayesian inference, Machine learning, Bayesian probability, Theoretical computer science, Algorithm, Unsupervised learning, Mathematics, Robot learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16722. Coaching the Exploration and Exploitation in Active Learning for Interactive Video Retrieval

- 标题：Coaching the Exploration and Exploitation in Active Learning for Interactive Video Retrieval
- 作者：Xiao-Yong Wei, Zhen-Qun Yang
- 年份：2012
- 出版日期：2012-10-05
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2012.2222902
- OpenAlex ID：https://openalex.org/W2109271964
- 落地页：https://doi.org/10.1109/tip.2012.2222902
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Advanced Image and Video Retrieval Techniques, Algorithms and Data Compression
- 关键词：Computer science, Schedule, Feature (linguistics), Artificial intelligence, Feature vector, Set (abstract data type), Machine learning, Active learning (machine learning), Domain (mathematical analysis), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Conventional active learning approaches for interactive video/image retrieval usually assume the query distribution is unknown, as it is difficult to estimate with only a limited number of labeled instances available. Thus, it is easy to put the system in a dilemma whether to explore the feature space in uncertain areas for a better understanding of the query distribution or to harvest in certain areas for more relevant instances. In this paper, we propose a novel approach called coached active learning that makes the query distribution predictable through training and, therefore, avoids the risk of searching on a completely unknown space. The estimated distribution, which provides a more global view of the feature space, can be used to schedule not only the timing but also the step sizes of the exploration and the exploitation in a principled way. The results of the experiments on a large-scale data set from TRECVID 2005-2009 validate the efficiency and effectiveness of our approach, which demonstrates an encouraging performance when facing domain-shift, outperforms eight conventional active learning methods, and shows superiority to six state-of-the-art interactive video retrieval systems.

## 16723. Classical Planning in MDP Heuristics: with a Little Help from Generalization

- 标题：Classical Planning in MDP Heuristics: with a Little Help from Generalization
- 作者：Andrey Kolobov, Mausam Mausam, Daniel S. Weld
- 年份：2010
- 出版日期：2010-05-05
- 类型：article
- 语言：en
- 来源：Proceedings of the International Conference on Automated Planning and Scheduling
- 来源类型：journal
- ISSN-L：2334-0835
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1609/icaps.v20i1.13424
- OpenAlex ID：https://openalex.org/W2109834196
- 落地页：https://doi.org/10.1609/icaps.v20i1.13424
- 开放 PDF 链接：https://ojs.aaai.org/index.php/ICAPS/article/download/13424/13273
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, AI-based Problem Solving and Planning, Reservoir Engineering and Simulation Methods
- 关键词：Heuristics, Generalization, Task (project management), Computer science, Bellman equation, Markov decision process, Artificial intelligence, Function (biology), Mathematical optimization, Upper and lower bounds, Robotics, Rule of thumb, Machine learning, Mathematics, Robot, Algorithm, Statistics, Markov process
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Computing a good policy in stochastic uncertain environments with unknown dynamics and reward model parameters is a challenging task. In a number of domains, ranging from space robotics to epilepsy management, it may be possible to have an initial training period when suboptimal performance is permitted. For such problems it is important to be able to identify when this training period is complete, and the computed policy can be used with high confidence in its future performance. A simple principled criteria for identifying when training has completed is when the error bounds on the value estimates of the current policy are sufficiently small that the optimal policy is fixed, with high probability. We present an upper bound on the amount of training data required to identify the optimal policy as a function of the unknown separation gap between the optimal and the next-best policy values. We illustrate with several small problems that by estimating this gap in an online manner, the number of training samples to provably reach optimality can be significantly lower than predicted offline using a Probably Approximately Correct framework that requires an input epsilon parameter.

## 16724. Adaptive Adversarial Multi-Armed Bandit Approach to Two-Person Zero-Sum Markov Games

- 标题：Adaptive Adversarial Multi-Armed Bandit Approach to Two-Person Zero-Sum Markov Games
- 作者：Hyeong Soo Chang, Jiaqiao Hu, Michael C. Fu, Steven I. Marcus
- 年份：2010
- 出版日期：2010-01-20
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Automatic Control
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9286
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tac.2009.2036333
- OpenAlex ID：https://openalex.org/W2109912732
- 落地页：https://doi.org/10.1109/tac.2009.2036333
- 主主题：Advanced Bandit Algorithms Research
- 主题：Advanced Bandit Algorithms Research, Reinforcement Learning in Robotics, Machine Learning and Algorithms
- 关键词：Zero-sum game, Markov chain, Convergence (economics), Zero (linguistics), Mathematical optimization, Mathematics, Markov decision process, Finite state, Sampling (signal processing), State space, Discrete mathematics, Markov process, Applied mathematics, Value (mathematics), Adversarial system, Computer science, Artificial intelligence, Nash equilibrium, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This technical note presents a recursive sampling-based algorithm for finite horizon two-person zero-sum Markov games (MGs) based on the Exp3 algorithm developed by Auer et al <i xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">.</i> for adaptive adversarial multi-armed bandit problems. We provide a finite-iteration bound to the equilibrium value of the induced ¿sample average approximation game¿ of a given MG and prove asymptotic convergence to the equilibrium value of the given MG. The time and space complexities of the algorithm are independent of the state space of the game.

## 16725. Multi-letter quantum finite automata: decidability of the equivalence and minimization of states

- 标题：Multi-letter quantum finite automata: decidability of the equivalence and minimization of states
- 作者：Daowen Qiu, Lvzhou Li, Xiangfu Zou, Paulo Mateus, Jozef Gruska
- 年份：2011
- 出版日期：2011-08-01
- 类型：article
- 语言：en
- 来源：Acta Informatica
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0001-5903
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00236-011-0139-6
- OpenAlex ID：https://openalex.org/W2110196476
- 落地页：https://doi.org/10.1007/s00236-011-0139-6
- 主主题：Quantum Computing Algorithms and Architecture
- 主题：Quantum Computing Algorithms and Architecture, Machine Learning and Algorithms, Computability, Logic, AI Algorithms
- 关键词：Decidability, Equivalence (formal languages), Mathematics, Combinatorics, Cardinality (data modeling), Alphabet, Theory of computation, Discrete mathematics, Nondeterministic finite automaton, Measure (data warehouse), Quantum finite automata, Automaton, Automata theory, Algorithm, Computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16726. Temporal logic robot control based on automata learning of environmental dynamics

- 标题：Temporal logic robot control based on automata learning of environmental dynamics
- 作者：Yushan Chen, Jana Tůmová, Alphan Ulusoy, Călin Belta
- 年份：2013
- 出版日期：2013-04-01
- 类型：article
- 语言：en
- 来源：The International Journal of Robotics Research
- 来源类型：journal
- 出版方：SAGE Publishing
- ISSN-L：0278-3649
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1177/0278364912473168
- OpenAlex ID：https://openalex.org/W2113261006
- 落地页：https://doi.org/10.1177/0278364912473168
- 主主题：Formal Methods in Verification
- 主题：Formal Methods in Verification, Machine Learning and Algorithms, semigroups and automata theory
- 关键词：Temporal logic, Linear temporal logic, Robot, Automaton, Computer science, Control (management), Learning automata, Artificial intelligence, Robotics, Fragment (logic), Control engineering, Theoretical computer science, Algorithm, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We develop a technique to automatically generate a control policy for a robot moving in an environment that includes elements with unknown, randomly changing behavior. The robot is required to achieve a surveillance mission, in which a certain request needs to be serviced repeatedly, while the expected time inbetween consecutive services is minimized and additional temporal logic constraints are satisfied. We define a fragment of linear temporal logic to describe such a mission and formulate the problem as a temporal logic game. Our approach is based on two main ideas. First, we extend results in automata learning to detect patterns of the unknown behavior of the elements in the environment. Second, we employ an automata–theoretic method to generate the control policy. We show that the obtained control policy converges to an optimal one when the partially unknown behavior patterns are fully learned. In addition, we illustrate the method in an experimental setup, in which an unmanned ground vehicle, with the help of a cooperating unmanned aerial vehicle (UAV), satisfies a temporal logic requirement in a partitioned environment whose regions are controlled by barriers with unknown behavior.

## 16727. Rademacher Chaos Complexities for Learning the Kernel Problem

- 标题：Rademacher Chaos Complexities for Learning the Kernel Problem
- 作者：Yiming Ying, Colin Campbell
- 年份：2010
- 出版日期：2010-08-30
- 类型：article
- 语言：en
- 来源：Neural Computation
- 来源类型：journal
- 出版方：The MIT Press
- ISSN-L：0899-7667
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1162/neco_a_00028
- OpenAlex ID：https://openalex.org/W2115390216
- 落地页：https://doi.org/10.1162/neco_a_00028
- 主主题：Control Systems and Identification
- 主题：Control Systems and Identification, Sparse and Compressive Sensing Techniques, Machine Learning and Algorithms
- 关键词：Mathematics, Generalization, Kernel (algebra), Entropy (arrow of time), Metric (unit), Applied mathematics, Artificial intelligence, Algorithm, Computer science, Discrete mathematics, Mathematical analysis
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We develop a novel generalization bound for learning the kernel problem. First, we show that the generalization analysis of the kernel learning problem reduces to investigation of the suprema of the Rademacher chaos process of order 2 over candidate kernels, which we refer to as Rademacher chaos complexity. Next, we show how to estimate the empirical Rademacher chaos complexity by well-established metric entropy integrals and pseudo-dimension of the set of candidate kernels. Our new methodology mainly depends on the principal theory of U-processes and entropy integrals. Finally, we establish satisfactory excess generalization bounds and misclassification error rates for learning gaussian kernels and general radial basis kernels.

## 16728. Enhancing instance-based classification with local density: a new algorithm for classifying unbalanced biomedical data

- 标题：Enhancing instance-based classification with local density: a new algorithm for classifying unbalanced biomedical data
- 作者：Claudia Plant, Christian Böhm, B. Tilg, Christian Baumgärtner
- 年份：2006
- 出版日期：2006-01-27
- 类型：article
- 语言：en
- 来源：Bioinformatics
- 来源类型：journal
- 出版方：Oxford University Press
- ISSN-L：1367-4803
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1093/bioinformatics/btl027
- OpenAlex ID：https://openalex.org/W2117416418
- 落地页：https://doi.org/10.1093/bioinformatics/btl027
- 开放 PDF 链接：https://academic.oup.com/bioinformatics/article-pdf/22/8/981/48841625/bioinformatics_22_8_981.pdf
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Machine Learning and Data Classification, Anomaly Detection Techniques and Applications
- 关键词：Outlier, Classifier (UML), Computer science, Artificial intelligence, Data mining, Pattern recognition (psychology), One-class classification, Class (philosophy), Cluster (spacecraft), Object (grammar), Algorithm, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
MOTIVATION: Classification is an important data mining task in biomedicine. In particular, classification on biomedical data often claims the separation of pathological and healthy samples with highest discriminatory performance for diagnostic issues. Even more important than the overall accuracy is the balance of a classifier, particularly if datasets of unbalanced class size are examined. RESULTS: We present a novel instance-based classification technique which takes both information of different local density of data objects and local cluster structures into account. Our method, which adopts the basic ideas of density-based outlier detection, determines the local point density in the neighborhood of an object to be classified and of all clusters in the corresponding region. A data object is assigned to that class where it fits best into the local cluster structure. The experimental evaluation on biomedical data demonstrates that our approach outperforms most popular classification methods. AVAILABILITY: The algorithm LCF is available for testing under http://biomed.umit.at/upload/lcfx.zip.

## 16729. CrowdMiner

- 标题：CrowdMiner
- 作者：Yael Amsterdamer, Yael S. Grossman, Tova Milo, Pierre Senellart
- 年份：2013
- 出版日期：2013-08-01
- 类型：article
- 语言：en
- 来源：Proceedings of the VLDB Endowment
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：2150-8097
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.14778/2536274.2536288
- OpenAlex ID：https://openalex.org/W2121431555
- 落地页：https://doi.org/10.14778/2536274.2536288
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Mobile Crowdsensing and Crowdsourcing, Machine Learning and Algorithms
- 关键词：Computer science, Ask price, Simple (philosophy), Context (archaeology), Data mining, Data science, Information retrieval
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This demo presents CrowdMiner, a system enabling the mining of interesting data patterns from the crowd. While traditional data mining techniques have been used extensively for finding patterns in classic databases, they are not always suitable for the crowd, mainly because humans tend to remember only simple trends and summaries rather than exact details. To address this, CrowdMiner employs a novel crowd-mining algorithm, designed specifically for this context. The algorithm iteratively chooses appropriate questions to ask the crowd, while aiming to maximize the knowledge gain at each step. We demonstrate CrowdMiner through a Well-Being portal, constructed interactively by mining the crowd, and in particular the conference participants, for common health related practices and trends.

## 16730. A Concealed Information Test with Combination of ERP Recording and Autonomic Measurements

- 标题：A Concealed Information Test with Combination of ERP Recording and Autonomic Measurements
- 作者：Ehsan Darestani Farahani, Mohammad Hassan Moradi
- 年份：2013
- 出版日期：2013-05-01
- 类型：article
- 语言：en
- 来源：Neurophysiology
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0090-2977
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11062-013-9360-y
- OpenAlex ID：https://openalex.org/W2122242849
- 落地页：https://doi.org/10.1007/s11062-013-9360-y
- 主主题：Deception detection and forensic psychology
- 主题：Deception detection and forensic psychology, Adversarial Robustness in Machine Learning, Psychopathy, Forensic Psychiatry, Sexual Offending
- 关键词：Skin conductance, Psychology, Context (archaeology), Linear discriminant analysis, Punishment (psychology), Electroencephalography, Cognitive psychology, Audiology, Artificial intelligence, Computer science, Developmental psychology, Neuroscience, Medicine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16731. Open Problems in Universal Induction &amp; Intelligence

- 标题：Open Problems in Universal Induction &amp; Intelligence
- 作者：Marcus Hütter
- 年份：2009
- 出版日期：2009-07-02
- 类型：article
- 语言：en
- 来源：Algorithms
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1999-4893
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/a2030879
- OpenAlex ID：https://openalex.org/W2132450394
- 落地页：https://doi.org/10.3390/a2030879
- 开放 PDF 链接：https://www.mdpi.com/1999-4893/2/3/879/pdf?version=1247079312
- 主主题：Computability, Logic, AI Algorithms
- 主题：Computability, Logic, AI Algorithms, Machine Learning and Algorithms, Evolutionary Algorithms and Applications
- 关键词：Computer science, Artificial intelligence, Inductive reasoning, Handwriting, Inference, Universal Turing machine, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Specialized intelligent systems can be found everywhere: finger print, handwriting, speech, and face recognition, spam filtering, chess and other game programs, robots, et al. This decade the first presumably complete mathematical theory of artificial intelligence based on universal induction-prediction-decision-action has been proposed. This informationtheoretic approach solidifies the foundations of inductive inference and artificial intelligence. Getting the foundations right usually marks a significant progress and maturing of a field. The theory provides a gold standard and guidance for researchers working on intelligent algorithms. The roots of universal induction have been laid exactly half-a-century ago and the roots of universal intelligence exactly one decade ago. So it is timely to take stock of what has been achieved and what remains to be done. Since there are already good recent surveys, I describe the state-of-the-art only in passing and refer the reader to the literature. This article concentrates on the open problems in universal induction and its extension to universal intelligence.

## 16732. A Simple and Faster Branch-and-Bound Algorithm for Finding a Maximum Clique with Computational Experiments

- 标题：A Simple and Faster Branch-and-Bound Algorithm for Finding a Maximum Clique with Computational Experiments
- 作者：Etsuji Tomita, Yoichi Sutani, Takanori Higashi, Mitsuo Wakatsuki
- 年份：2013
- 出版日期：2013-01-01
- 类型：article
- 语言：en
- 来源：IEICE Transactions on Information and Systems
- 来源类型：journal
- 出版方：Institute of Electronics, Information and Communication Engineers
- ISSN-L：0916-8532
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1587/transinf.e96.d.1286
- OpenAlex ID：https://openalex.org/W2143365024
- 落地页：https://doi.org/10.1587/transinf.e96.d.1286
- 开放 PDF 链接：https://www.jstage.jst.go.jp/article/transinf/E96.D/6/E96.D_1286/_pdf
- 主主题：Complexity and Algorithms in Graphs
- 主题：Complexity and Algorithms in Graphs, Machine Learning and Algorithms, Optimization and Search Problems
- 关键词：Clique problem, Computer science, Clique, Algorithm, Overhead (engineering), Simple (philosophy), Branch and bound, Graph, Chordal graph, Theoretical computer science, Mathematics, Combinatorics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Many problems can be formulated as maximum clique problems. Hence, it is highly important to develop algorithms that can find a maximum clique very fast in practice. We propose new approximate coloring and other related techniques which markedly improve the run time of the branch-and-bound algorithm MCR (J. Global Optim., 37, pp.95-111, 2007), previously shown to be the fastest maximum-clique-finding algorithm for a large number of graphs. The algorithm obtained by introducing these new techniques in MCR is named MCS. It is shown that MCS is successful in reducing the search space quite efficiently with low overhead. Extensive computational experiments confirm the superiority of MCS over MCR and other existing algorithms. It is faster than the other algorithms by orders of magnitude for several graphs. In particular, it is faster than MCR for difficult graphs of very high density and for very large and sparse graphs, even though MCS is not designed for any particular type of graph. MCS can be faster than MCR by a factor of more than 100,000 for some extremely dense random graphs. This paper demonstrates in detail the effectiveness of each new techniques in MCS, as well as the overall contribution.

## 16733. Optimal Algorithms for Two Group Testing Problems, and New Bounds on Generalized Superimposed Codes

- 标题：Optimal Algorithms for Two Group Testing Problems, and New Bounds on Generalized Superimposed Codes
- 作者：Annalisa De Bonis, Ugo Vaccaro
- 年份：2006
- 出版日期：2006-09-29
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tit.2006.881740
- OpenAlex ID：https://openalex.org/W2143609028
- 落地页：https://doi.org/10.1109/tit.2006.881740
- 主主题：SARS-CoV-2 detection and testing
- 主题：SARS-CoV-2 detection and testing, Advanced biosensing and bioanalysis techniques, Machine Learning and Algorithms
- 关键词：Group testing, Generalization, Context (archaeology), Algorithm, Set (abstract data type), Group (periodic table), Decoding methods, Computer science, Mathematics, Randomized algorithm, Deterministic algorithm, Theoretical computer science, Discrete mathematics, Combinatorics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Two variants of the well-known group testing problem are considered. In the first variant a finite set of items O and an unknown subset PsubeO are given, and one wants to identify the set P by asking the least number of questions of the form "Is |QcapP|=1?", where QsubeO. This problem naturally arises in the design of efficient contention resolution algorithms for certain random multiple-access communication systems [Berger et al. "Random multiple-access communication and group testing," IEEE Trans. Commun., vol. 32, no. 7, pp. 769-779, 1984]. In the second variant of the problem, the answer to the question "Is |QcapP|=1?" is correctly YES if |QcapP|=1 and NO if |QcapP|=0", and it is left to a (possibly malicious) adversary otherwise. This model was introduced in [Damaschke, "Randomized group testing for mutually obscuring defectives", Inf. Process. Lett., vol. 67, pp. 131-135, 1998], in the context of chemical compound testing. In this correspondence several algorithms for these group testing problems are presented, trying to optimize different measures of performance: The overall number of tests performed by the algorithm, the number of stages in which tests can be arranged, and the decoding complexity of identifying the elements of P from tests outcomes. Some of the given algorithms are optimal with respect to more than one of the above criteria. Instrumental to the results presented in the correspondence are new and improved bounds on certain generalization of superimposed codes introduced in [Dyachkov and Rykov, "A generalization of superimposed codes and its application to the multiple-access channel", in Proc. 1984 IEEE Int. Symp. Inf. Theory, pp. 62-64], [De Bonis and Vaccaro, "Constructions of generalized superimposed codes with applications to group testing and conflict resolution in multiple access channels", Theoretic. Comput. Sci., vol. 306, no. 1-3, pp. 223-243, 2003] a result that it is believed to be of independent interest

## 16734. Reaction Times and Deception - the Lying Constant

- 标题：Reaction Times and Deception - the Lying Constant
- 作者：Martin R. Sheridan, Kenneth A. Flowers
- 年份：2010
- 出版日期：2010-11-21
- 类型：article
- 语言：en
- 来源：International Journal of Psychological Studies
- 来源类型：journal
- 出版方：Canadian Center of Science and Education
- ISSN-L：1918-7211
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.5539/ijps.v2n2p41
- OpenAlex ID：https://openalex.org/W2152262169
- 落地页：https://doi.org/10.5539/ijps.v2n2p41
- 开放 PDF 链接：https://ccsenet.org/journal/index.php/ijps/article/download/6498/6362
- 主主题：Deception detection and forensic psychology
- 主题：Deception detection and forensic psychology, Psychopathy, Forensic Psychiatry, Sexual Offending, Adversarial Robustness in Machine Learning
- 关键词：Lying, Deception, Lie detection, Psychology, Constant (computer programming), Task (project management), Social psychology, Cognition, Process (computing), Cognitive psychology, Computer science, Neuroscience
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The cognitive theory of lie detection suggests that it takes longer on average to formulate a deliberately falseresponse than a truthful one because it requires the truth to first be known and then altered, adding an extracomponent to the response process. This concept was upheld in a modified form in three experiments wheresubjects indicated as quickly as possible whether presented numbers were higher or lower than a given standardnumber, and to “lie” (give the wrong answer deliberately) on half the trials. Results suggested that lying adds aconstant additional time to reaction times (RTs) independently of other factors such as the complexity of thecognitive task or method of response. Additionally, true Yes RTs were shorter than true No ones, producing aninteraction with the lying constant such that RTs could reliably distinguish truth from lies for Yes responses butnot so easily for No responses.

## 16735. An Experimental Study of K* Algorithm

- 标题：An Experimental Study of K* Algorithm
- 作者：Dayana C. Tejera Hernández
- 年份：2015
- 出版日期：2015-03-08
- 类型：article
- 语言：en
- 来源：International Journal of Information Engineering and Electronic Business
- 来源类型：journal
- ISSN-L：2074-9023
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.5815/ijieeb.2015.02.03
- OpenAlex ID：https://openalex.org/W2162797630
- 落地页：https://doi.org/10.5815/ijieeb.2015.02.03
- 开放 PDF 链接：http://www.mecs-press.org/ijieeb/ijieeb-v7-n2/IJIEEB-V7-N2-3.pdf
- 主主题：Data Mining Algorithms and Applications
- 主题：Data Mining Algorithms and Applications, Imbalanced Data Classification Techniques, Machine Learning and Data Classification
- 关键词：Computer science, Star (game theory), Naive Bayes classifier, Smoothness, Class (philosophy), Algorithm, Machine learning, Artificial intelligence, Support vector machine, k-nearest neighbors algorithm, Data mining, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Machine Learning techniques are taking place in all areas of our lives, to help us to make decisions. There is a large number of algorithms available for multiple purposes and appropriate for specific data types. That is why it is required to pay special attention to decide which is the recommended technique, to use in each case. K Star is an instance-based learner that tries to improve its performance for dealing with missing values, smoothness problems and both real and symbolic valued attributes; but it is not known much information about how the way it faces attribute and class noisy, and with mixed values of the attributes in the datasets. In this paper we made six experiments with Weka, to compare K Star and other important algorithms: Nave Bayes, C4.5, Support Vector Machines and k-Nearest Neighbors, taking into account its performance classifying datasets with those features. As a result, K Star demonstrated to be the best of them in dealing with noisy attributes and with imbalanced attributes.

## 16736. On reoptimizing multi-class classifiers

- 标题：On reoptimizing multi-class classifiers
- 作者：Chris Bourke, Kun Deng, Stephen Scott, Robert E. Schapire, N. V. Vinodchandran
- 年份：2008
- 出版日期：2008-04-15
- 类型：article
- 语言：en
- 来源：Machine Learning
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-6125
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1007/s10994-008-5056-8
- OpenAlex ID：https://openalex.org/W2166295897
- 落地页：https://doi.org/10.1007/s10994-008-5056-8
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s10994-008-5056-8.pdf
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Machine Learning and Algorithms, Machine Learning and Data Classification
- 关键词：Heuristics, Mathematics, Classifier (UML), Binary classification, Mathematical optimization, Quadratic function, Quadratic equation, Hypersurface, Binary number, Algorithm, Computer science, Artificial intelligence, Support vector machine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16737. Transition Matrices of Sequential Machines

- 标题：Transition Matrices of Sequential Machines
- 作者：S. Seshu, Raymond E. Miller, Gernot Metze
- 年份：1959
- 出版日期：1959-01-01
- 类型：article
- 语言：en
- 来源：IRE Transactions on Circuit Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0096-2007
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tct.1959.1086510
- OpenAlex ID：https://openalex.org/W2168776529
- 落地页：https://doi.org/10.1109/tct.1959.1086510
- 主主题：Computability, Logic, AI Algorithms
- 主题：Computability, Logic, AI Algorithms, Formal Methods in Verification, Machine Learning and Algorithms
- 关键词：Matrix multiplication, Stochastic matrix, State (computer science), Invariant (physics), Matrix (chemical analysis), Asynchronous communication, Relation (database), Computer science, Algebra over a field, Matrix analysis, Mathematics, Algorithm, Pure mathematics, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this paper a matrix technique is introduced for the analysis of state diagrams of synchronous sequential machines. The matrices introduced are closely related to the relation matrices of the calculus of relations and provide a formal tool for discussing state diagrams. It is shown that several of the well-known theorems on state diagrams are consequences of properties of transition matrices, which remain invariant under matrix multiplication. A reduction procedure for state diagrams, based on transition matrices, which is similar to Moore's technique, is given. A method of extending the results to asynchronous machines is also included.

## 16738. Matrix Completion With Column Manipulation: Near-Optimal Sample-Robustness-Rank Tradeoffs

- 标题：Matrix Completion With Column Manipulation: Near-Optimal Sample-Robustness-Rank Tradeoffs
- 作者：Yudong Chen, Huan Xu, Constantine Caramanis, Sujay Sanghavi
- 年份：2015
- 出版日期：2015-11-10
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tit.2015.2499247
- OpenAlex ID：https://openalex.org/W2221507943
- 落地页：https://doi.org/10.1109/tit.2015.2499247
- 主主题：Sparse and Compressive Sensing Techniques
- 主题：Sparse and Compressive Sensing Techniques, Optimization and Search Problems, Machine Learning and Algorithms
- 关键词：Matrix completion, Robustness (evolution), Fraction (chemistry), Matrix (chemical analysis), Algorithm, Skew, Matrix norm, Mathematics, Trimming, Computer science, Rank (graph theory), Column (typography), Mathematical optimization, Combinatorics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This paper considers the problem of matrix completion when some number of the columns are completely and arbitrarily corrupted, potentially by a malicious adversary. It is well known that standard algorithms for matrix completion can return arbitrarily poor results, if even a single column is corrupted. One direct application comes from robust collaborative filtering. Here, some number of users are so-called manipulators who try to skew the predictions of the algorithm by calibrating their inputs to the system. In this paper, we develop an efficient algorithm for this problem based on a combination of a trimming procedure and a convex program that minimizes the nuclear norm and the ℓ <sub xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">1,2</sub> norm. Our theoretical results show that given a vanishing fraction of observed entries, it is nevertheless possible to complete the underlying matrix even when the number of corrupted columns grows. Significantly, our results hold without any assumptions on the locations or values of the observed entries of the manipulated columns. Moreover, we show by an information-theoretic argument that our guarantees are nearly optimal in terms of the fraction of sampled entries on the authentic columns, the fraction of corrupted columns, and the rank of the underlying matrix. Our results therefore sharply characterize the tradeoffs between sample, robustness, and rank in matrix completion.

## 16739. Adaptive structure metrics for automated feedback provision in intelligent tutoring systems

- 标题：Adaptive structure metrics for automated feedback provision in intelligent tutoring systems
- 作者：Benjamin Paaßen, Bassam Mokbel, Barbara Hammer
- 年份：2016
- 出版日期：2016-03-03
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.neucom.2015.12.108
- OpenAlex ID：https://openalex.org/W2234183288
- 落地页：https://doi.org/10.1016/j.neucom.2015.12.108
- 主主题：Intelligent Tutoring Systems and Adaptive Learning
- 主题：Intelligent Tutoring Systems and Adaptive Learning, Online Learning and Analytics, Machine Learning and Algorithms
- 关键词：Computer science, Construct (python library), Set (abstract data type), Adaptation (eye), Machine learning, ENCODE, Domain (mathematical analysis), Artificial intelligence, Metric (unit), Java, Similarity (geometry), Intelligent tutoring system, Data mining, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16740. Hadoop based Feature Selection and Decision Making Models on Big Data

- 标题：Hadoop based Feature Selection and Decision Making Models on Big Data
- 作者：Thulasi Bikku, N. Sambasiva Rao, Ananda Rao Akepogu
- 年份：2016
- 出版日期：2016-03-18
- 类型：article
- 语言：en
- 来源：Indian Journal of Science and Technology
- 来源类型：journal
- 出版方：Indian Society for Education and Environment
- ISSN-L：0974-5645
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.17485/ijst/2016/v9i10/88905
- OpenAlex ID：https://openalex.org/W2303326261
- 落地页：https://doi.org/10.17485/ijst/2016/v9i10/88905
- 开放 PDF 链接：http://www.indjst.org/index.php/indjst/article/download/88905/67963
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Imbalanced Data Classification Techniques, Data Stream Mining Techniques
- 关键词：Computer science, Big data, Feature selection, Data mining, Selection (genetic algorithm), Decision tree, Dimension (graph theory), Feature (linguistics), Computation, Volume (thermodynamics), Class (philosophy), Machine learning, Artificial intelligence, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Objectives: A large amount of informative data is being captured and processed by today’s organizations and is continuing to increase exponentially. It becomes computationally inaccurate to analyze such big data for decision making systems. Methods/Analysis: Hadoop, which is a working model based on the Map-Reduce framework with efficient computation and processing of Big Data. Findings: Most of the traditional classification algorithms have issues such as class imbalance and dimension reduction on Big Data. However, a large part of the data produced today are incomplete and inaccurate, so large organizations prefer relational databases to store their information, but the user query processing speed is very low. Unlike existing solutions that require a prior knowledge of classification accuracy for various types of data characteristics, which is impossible to obtain in practice. Applications/Improvement: In this paper, we have given a compared proposed model to different big data feature selection and classification models along with advantages and limitations. Keywords: Big Data, Decision Tree, Feature Selection, Hadoop, MapReduce

## 16741. Simulated Annealing Optimization for Hydrocarbon Pipeline Networks

- 标题：Simulated Annealing Optimization for Hydrocarbon Pipeline Networks
- 作者：Diego Rodríguez, Paola P. Oteiza, Nélida B. Brignole
- 年份：2013
- 出版日期：2013-05-24
- 类型：article
- 语言：en
- 来源：Industrial & Engineering Chemistry Research
- 来源类型：journal
- 出版方：American Chemical Society
- ISSN-L：0888-5885
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1021/ie400022g
- OpenAlex ID：https://openalex.org/W2323784994
- 落地页：https://doi.org/10.1021/ie400022g
- 主主题：Water Systems and Optimization
- 主题：Water Systems and Optimization, Machine Learning and Algorithms, Optimization and Packing Problems
- 关键词：Simulated annealing, Pipeline (software), Computer science, Mathematical optimization, Metaheuristic, Gasoline, Pipeline transport, Annealing (glass), Algorithm, Hydrocarbon, Environmental science, Materials science, Mathematics, Chemistry, Engineering, Environmental engineering, Waste management
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this work the determination of optimally located pipeline networks has been proposed by means of the implementation of a metaheuristic algorithm called Simulated Annealing with GAMS (SAG) in order to find the best pipeline layout together with a subset of locations to install concentrating nodes. The strategy essentially consists of a hybridization of Simulated Annealing, combined with the well-known GAMS package. In particular, the sample cases consisted of finding the most convenient routes so as to transport natural gasoline from Santa Cruz (Argentina) gas fields to the processing plants. The SAG algorithm behaved satisfactorily because it proved to be efficient and flexible.

## 16742. Statistical ranking using the $l^{1}$-norm on graphs

- 标题：Statistical ranking using the $l^{1}$-norm on graphs
- 作者：Braxton Osting, Jérôme Darbon, Stanley Osher
- 年份：2013
- 出版日期：2013-01-01
- 类型：article
- 语言：en
- 来源：Inverse Problems and Imaging
- 来源类型：journal
- 出版方：American Institute of Mathematical Sciences
- ISSN-L：1930-8337
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.3934/ipi.2013.7.907
- OpenAlex ID：https://openalex.org/W2332835381
- 落地页：https://doi.org/10.3934/ipi.2013.7.907
- 主主题：Sparse and Compressive Sensing Techniques
- 主题：Sparse and Compressive Sensing Techniques, Machine Learning and Algorithms, Statistical Methods and Inference
- 关键词：Pairwise comparison, Computer science, Residual, Combinatorics, Mathematics, Graph, Statistical model, Mathematical optimization, Algorithm, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We consider the problem of establishing a statistical ranking for a set of alternatives from a dataset which consists of an (inconsistent and incomplete) set of quantitative pairwise comparisons of the alternatives. If we consider the directed graph where vertices represent the alternatives and the pairwise comparison data is a function on the arcs, then the statistical ranking problem is to find a potential function, defined on the vertices, such that the gradient of the potential optimally agrees with the pairwise comparisons. Potentials, optimal in the $l^{2}$-norm sense, can be found by solving a least-squares problem on the digraph and, recently, the residual has been interpreted using the Hodge decomposition (Jiang et. al., 2010). In this work, we consider an $l^{1}$-norm formulation of the statistical ranking problem. We describe a fast graph-cut approach for finding $\epsilon$-optimal solutions, which has been used successfully in image processing and computer vision problems. Applying this method to several datasets, we demonstrate its efficacy at finding solutions with sparse residual.

## 16743. Incremental and Decremental Max-Flow for Online Semi-Supervised Learning

- 标题：Incremental and Decremental Max-Flow for Online Semi-Supervised Learning
- 作者：Lei Zhu, Shaoning Pang, Abdolhossein Sarrafzadeh, Tao Ban, Daisuke Inoue
- 年份：2016
- 出版日期：2016-04-15
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Knowledge and Data Engineering
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：1041-4347
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tkde.2016.2550042
- OpenAlex ID：https://openalex.org/W2338948909
- 落地页：https://doi.org/10.1109/tkde.2016.2550042
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Machine Learning and Data Classification, Anomaly Detection Techniques and Applications
- 关键词：Computer science, Retraining, Graph, Data stream mining, Machine learning, Artificial intelligence, Semi-supervised learning, Labeled data, Data stream, Supervised learning, Maximum flow problem, Flow (mathematics), Online algorithm, Online learning, Algorithm, Theoretical computer science, Mathematics, Artificial neural network, Mathematical optimization
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Max-flow has been adopted for semi-supervised data modelling, yet existing algorithms were derived only for the learning from static data. This paper proposes an online max-flow algorithm for the semi-supervised learning from data streams. Consider a graph learned from labelled and unlabelled data, and the graph being updated dynamically for accommodating online data adding and retiring. In learning from the resulting non stationary graph, we augment and de-augment paths to update max-flow with a theoretical guarantee that the updated max-flow equals to that from batch retraining. For classification, we compute min-cut over current max-flow, so that minimized number of similar sample pairs are classified into distinct classes. Empirical evaluation on real-world data reveals that our algorithm outperforms state-of-the-art stream classification algorithms.

## 16744. A non-parametric approach to extending generic binary classifiers for multi-classification

- 标题：A non-parametric approach to extending generic binary classifiers for multi-classification
- 作者：Venkataraman Santhanam, Vlad I. Morariu, David Harwood, Larry S. Davis
- 年份：2016
- 出版日期：2016-04-29
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2016.04.008
- OpenAlex ID：https://openalex.org/W2339446260
- 落地页：https://doi.org/10.1016/j.patcog.2016.04.008
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Anomaly Detection Techniques and Applications, Machine Learning and Data Classification
- 关键词：Pattern recognition (psychology), Artificial intelligence, Computer science, Probabilistic logic, Classifier (UML), Binary classification, Binary number, Parametric statistics, Probabilistic classification, Random subspace method, Multiclass classification, Support vector machine, Machine learning, Mathematics, Naive Bayes classifier, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16745. Learning Moore machines from input–output traces

- 标题：Learning Moore machines from input–output traces
- 作者：Georgios Giantamidis, Stavros Tripakis, Stylianos Basagiannis
- 年份：2019
- 出版日期：2019-11-06
- 类型：article
- 语言：en
- 来源：International Journal on Software Tools for Technology Transfer
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1433-2779
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10009-019-00544-0
- OpenAlex ID：https://openalex.org/W2403966573
- 落地页：https://doi.org/10.1007/s10009-019-00544-0
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Optimization and Search Problems, Ferroelectric and Negative Capacitance Devices
- 关键词：Computer science, Automaton, Finite-state machine, Theory of computation, Algorithm, Learning automata, Artificial intelligence, Set (abstract data type), Machine learning, Equivalence (formal languages), Abstract machine, Class (philosophy), Carry (investment), Identification (biology), State (computer science), Mathematics, Discrete mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16746. Automated Menu Planning Algorithm for Children: Food Recommendation by Dietary Management System using ID3 for Indian Food Database

- 标题：Automated Menu Planning Algorithm for Children: Food Recommendation by Dietary Management System using ID3 for Indian Food Database
- 作者：Ashvini Kale, Nisha Auti
- 年份：2015
- 出版日期：2015-01-01
- 类型：article
- 语言：en
- 来源：Procedia Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1877-0509
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1016/j.procs.2015.04.070
- OpenAlex ID：https://openalex.org/W242456420
- 落地页：https://doi.org/10.1016/j.procs.2015.04.070
- 主主题：Data Mining Algorithms and Applications
- 主题：Data Mining Algorithms and Applications, Artificial Intelligence in Healthcare, Machine Learning and Data Classification
- 关键词：Computer science, ID3, Malnutrition, Java, Malnutrition in children, Management system, Database, Algorithm, Decision tree, Artificial intelligence, Medicine, Operations management, Decision tree learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Adequate nutrition is essential in early childhood for the proper body growth and organ formation, to have a strong immune system, cognitive and neurological development. Children in India are mostly suffered from malnutrition. It happens because most of the mothers don’t have proper knowledge about nutrition facts, which is to be feed to her child. To give proper diet to children as per their profile, Dietary Management System using ID3 is proposed. In this paper, ID3 is implemented with an example of Beverages using Weka tool and proposed work will be implemented in JAVA.

## 16747. Object Frequency and Predictability Effects on Eye Fixation Durations in Real-World Scene Viewing

- 标题：Object Frequency and Predictability Effects on Eye Fixation Durations in Real-World Scene Viewing
- 作者：Hsueh‐Cheng Wang, Alex D. Hwang, Marc Pomplun
- 年份：2010
- 出版日期：2010-07-13
- 类型：article
- 语言：en
- 来源：Journal of Eye Movement Research
- 来源类型：journal
- 出版方：Bern Open Publishing
- ISSN-L：1995-8692
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.16910/jemr.3.3.3
- OpenAlex ID：https://openalex.org/W2438813371
- 落地页：https://doi.org/10.16910/jemr.3.3.3
- 开放 PDF 链接：https://bop.unibe.ch/JEMR/article/download/2297/3493
- 主主题：Gaze Tracking and Assistive Technology
- 主题：Gaze Tracking and Assistive Technology, Visual Attention and Saliency Detection, Multimodal Machine Learning Applications
- 关键词：Predictability, Gaze, Fixation (population genetics), Eye movement, Computer science, Word lists by frequency, Eye tracking, Artificial intelligence, Duration (music), Cognitive psychology, Latent semantic analysis, Reading (process), Computer vision, Speech recognition, Natural language processing, Psychology, Linguistics, Mathematics, Statistics, Art
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
During text reading, the durations of eye fixations decrease with greater frequency and predictability of the currently fixated word (Rayner, 1998; 2009). However, it has not been tested whether those results also apply to scene viewing. We computed object frequency and predictability from both linguistic and visual scene analysis (LabelMe, Russell et al., 2008), and Latent Semantic Analysis (Landauer et al., 1998) was applied to estimate predictability. In a scene-viewing experiment, we found that, for small objects, linguistics-based frequency, but not scene-based frequency, had effects on first fixation duration, gaze duration, and total time. Both linguistic and scene-based predictability affected total time. Similar to reading, fixation duration decreased with higher frequency and predictability. For large objects, we found the direction of effects to be the inverse of those found in reading studies. These results suggest that the recognition of small objects in scene viewing shares some characteristics with the recognition of words in reading.

## 16748. LSTM-in-LSTM for generating long descriptions of images

- 标题：LSTM-in-LSTM for generating long descriptions of images
- 作者：Jun Song, Siliang Tang, Jun Xiao, Fei Wu, Zhongfei Zhang
- 年份：2016
- 出版日期：2016-08-30
- 类型：article
- 语言：en
- 来源：Computational Visual Media
- 来源类型：journal
- 出版方：Springer Nature
- ISSN-L：2096-0433
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1007/s41095-016-0059-z
- OpenAlex ID：https://openalex.org/W2508514999
- 落地页：https://doi.org/10.1007/s41095-016-0059-z
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s41095-016-0059-z.pdf
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Benchmark (surveying), Artificial intelligence, Word (group theory), Context (archaeology), Natural language processing, Architecture, Pattern recognition (psychology), Speech recognition, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this paper, we propose an approach for generating rich fine-grained textual descriptions of images. In particular, we use an LSTM-in-LSTM (long short-term memory) architecture, which consists of an inner LSTM and an outer LSTM. The inner LSTM effectively encodes the long-range implicit contextual interaction between visual cues (i.e., the spatiallyconcurrent visual objects), while the outer LSTM generally captures the explicit multi-modal relationship between sentences and images (i.e., the correspondence of sentences and images). This architecture is capable of producing a long description by predicting one word at every time step conditioned on the previously generated word, a hidden vector (via the outer LSTM), and a context vector of fine-grained visual cues (via the inner LSTM). Our model outperforms state-of-theart methods on several benchmark datasets (Flickr8k, Flickr30k, MSCOCO) when used to generate long rich fine-grained descriptions of given images in terms of four different metrics (BLEU, CIDEr, ROUGE-L, and METEOR).

## 16749. Online regularized learning with pairwise loss functions

- 标题：Online regularized learning with pairwise loss functions
- 作者：Zheng-Chu Guo, Yiming Ying, Ding‐Xuan Zhou
- 年份：2016
- 出版日期：2016-08-15
- 类型：article
- 语言：en
- 来源：Advances in Computational Mathematics
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1019-7168
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10444-016-9479-7
- OpenAlex ID：https://openalex.org/W2513039057
- 落地页：https://doi.org/10.1007/s10444-016-9479-7
- 主主题：Sparse and Compressive Sensing Techniques
- 主题：Sparse and Compressive Sensing Techniques, Advanced Bandit Algorithms Research, Machine Learning and Algorithms
- 关键词：Pairwise comparison, Scalability, Reproducing kernel Hilbert space, Mathematics, Regularization (linguistics), Computer science, Kernel (algebra), Theoretical computer science, Convergence (economics), Algorithm, Machine learning, Hilbert space, Mathematical optimization, Artificial intelligence, Discrete mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16750. Random Multi-Graphs: A semi-supervised learning framework for classification of high dimensional data

- 标题：Random Multi-Graphs: A semi-supervised learning framework for classification of high dimensional data
- 作者：Qin Zhang, Jianyuan Sun, Guoqiang Zhong, Junyu Dong
- 年份：2016
- 出版日期：2016-08-31
- 类型：article
- 语言：en
- 来源：Image and Vision Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0262-8856
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.imavis.2016.08.006
- OpenAlex ID：https://openalex.org/W2513897596
- 落地页：https://doi.org/10.1016/j.imavis.2016.08.006
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Domain Adaptation and Few-Shot Learning, Machine Learning and Data Classification
- 关键词：Computer science, Dimensionality reduction, Randomness, Graph, Semi-supervised learning, Artificial intelligence, Machine learning, Regularization (linguistics), Theoretical computer science, Curse of dimensionality, Feature selection, Data mining, Pattern recognition (psychology), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16751. A Hybrid Approach for Path Vulnerability Matrix on Random Key Predistribution for Wireless Sensor Networks

- 标题：A Hybrid Approach for Path Vulnerability Matrix on Random Key Predistribution for Wireless Sensor Networks
- 作者：Priyanka Ahlawat, Mayank Dave
- 年份：2016
- 出版日期：2016-10-07
- 类型：article
- 语言：en
- 来源：Wireless Personal Communications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0929-6212
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11277-016-3779-6
- OpenAlex ID：https://openalex.org/W2528296128
- 落地页：https://doi.org/10.1007/s11277-016-3779-6
- 主主题：Security in Wireless Sensor Networks
- 主题：Security in Wireless Sensor Networks, Network Security and Intrusion Detection, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Vulnerability (computing), Wireless sensor network, Computer network, Path (computing), Node (physics), Distributed computing, Key (lock), Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16752. A semantic framework for noise addition with nominal data

- 标题：A semantic framework for noise addition with nominal data
- 作者：Mercedes Rodríguez-García, Montserrat Batet, David Sánchez
- 年份：2017
- 出版日期：2017-01-24
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.knosys.2017.01.032
- OpenAlex ID：https://openalex.org/W2581812954
- 落地页：https://doi.org/10.1016/j.knosys.2017.01.032
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Explainable Artificial Intelligence (XAI), Data Mining Algorithms and Applications
- 关键词：Noise (video), Overfitting, Computer science, Realization (probability), Semantics (computer science), Data mining, Algorithm, Artificial intelligence, Statistics, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16753. Stream-based semi-supervised learning for recommender systems

- 标题：Stream-based semi-supervised learning for recommender systems
- 作者：Paweł J. Matuszyk, Myra Spiliopoulou
- 年份：2017
- 出版日期：2017-02-02
- 类型：article
- 语言：en
- 来源：Machine Learning
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-6125
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1007/s10994-016-5614-4
- OpenAlex ID：https://openalex.org/W2585837637
- 落地页：https://doi.org/10.1007/s10994-016-5614-4
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s10994-016-5614-4.pdf
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Recommender Systems and Techniques, Machine Learning and Data Classification
- 关键词：Computer science, Recommender system, Machine learning, Matrix decomposition, Artificial intelligence, Supervised learning, Quality (philosophy), Semi-supervised learning, Data stream, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16754. Bat Q-learning Algorithm

- 标题：Bat Q-learning Algorithm
- 作者：Bilal H. Abed-alguni
- 年份：2017
- 出版日期：2017-01-01
- 类型：article
- 语言：en
- 来源：Jordanian Journal of Computers and Information Technology
- 来源类型：journal
- ISSN-L：2413-9351
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.5455/jjcit.71-1480540385
- OpenAlex ID：https://openalex.org/W2595292627
- 落地页：https://doi.org/10.5455/jjcit.71-1480540385
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Reinforcement Learning in Robotics, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Algorithm, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Cooperative Q-learning approach allows multiple learners to learn independently then share their Q-values among each other using a Q-value sharing strategy. A main problem with this approach is that the solutions of the learners may not converge to optimality because the optimal Q-values may not be found. Another problem is that some cooperative algorithms perform very well with single-task problems, but quite poorly with multi-task problems. This paper proposes a new cooperative Q-learning algorithm called the Bat Q-learning algorithm (BQ-learning) that implements a Q-value sharing strategy based on the Bat algorithm. The Bat algorithm is a powerful optimization algorithm that increases the possibility of finding the optimal Q-values by balancing between the exploration and exploitation of actions by tuning the parameters of the algorithm. The BQ-learning algorithm was tested using two problems: the shortest path problem (single-task problem) and the taxi problem (multi-task problem). The experimental results suggest that BQ-learning performs better than single-agent Q-learning and some well-known cooperative Q-learning algorithms.

## 16755. Proteus: Exploiting precision variability in deep neural networks

- 标题：Proteus: Exploiting precision variability in deep neural networks
- 作者：Patrick Judd, Jorge Albericio, Tayler Hetherington, Tor M. Aamodt, Natalie Enright Jerger, Raquel Urtasun, Andreas Moshovos
- 年份：2017
- 出版日期：2017-05-24
- 类型：article
- 语言：en
- 来源：Parallel Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-8191
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.parco.2017.05.003
- OpenAlex ID：https://openalex.org/W2618636670
- 落地页：https://doi.org/10.1016/j.parco.2017.05.003
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Adversarial Robustness in Machine Learning, Stochastic Gradient Optimization Techniques
- 关键词：Computer science, Memory footprint, Inference, Convolutional neural network, Artificial neural network, Proteus, Efficient energy use, Floating point, Computer engineering, Real-time computing, Algorithm, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16756. Parallel interactive retrieval of item and associative information from event memory

- 标题：Parallel interactive retrieval of item and associative information from event memory
- 作者：Gregory E. Cox, Amy H. Criss
- 年份：2017
- 出版日期：2017-06-22
- 类型：article
- 语言：en
- 来源：Cognitive Psychology
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0010-0285
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.cogpsych.2017.05.004
- OpenAlex ID：https://openalex.org/W2662645865
- 落地页：https://doi.org/10.1016/j.cogpsych.2017.05.004
- 主主题：Memory Processes and Influences
- 主题：Memory Processes and Influences, Machine Learning and Algorithms, Topic Modeling
- 关键词：Associative property, Computer science, Content-addressable memory, Facilitation, Cognition, Matching (statistics), Cognitive models of information retrieval, Cognitive psychology, Information retrieval, Artificial intelligence, Psychology, Human–computer information retrieval, Mathematics, Artificial neural network, Neuroscience, Search engine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16757. Diverse classifier ensemble creation based on heuristic dataset modification

- 标题：Diverse classifier ensemble creation based on heuristic dataset modification
- 作者：Hamid Jamalinia, Saber Khalouei, Vahideh Rezaie, Samad Nejatian, Karamolah Bagherifard, Hamïd Parvïn
- 年份：2017
- 出版日期：2017-08-16
- 类型：article
- 语言：en
- 来源：Journal of Applied Statistics
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0266-4763
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1080/02664763.2017.1363163
- OpenAlex ID：https://openalex.org/W2747360225
- 落地页：https://doi.org/10.1080/02664763.2017.1363163
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Imbalanced Data Classification Techniques, Data Stream Mining Techniques
- 关键词：Boosting (machine learning), Computer science, Classifier (UML), Machine learning, Artificial intelligence, Ensemble learning, Decision tree, Generalization error, Training set, Perceptron, Margin classifier, Gradient boosting, Cascading classifiers, Pattern recognition (psychology), Random subspace method, Data mining, Artificial neural network, Random forest
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Bagging and Boosting are two main ensemble approaches consolidating the decisions of several hypotheses. The diversity of the ensemble members is considered to be a significant element to obtain generalization error. Here, an inventive method called EBAGTS (ensemble-based artificially generated training samples) is proposed to generate ensembles. It manipulates training examples in three ways in order to build various hypotheses straightforwardly: drawing a sub-sample from training set, reducing/raising error-prone training instances, and reducing/raising local instances around error-prone regions. The proposed method is a straightforward, generic framework utilizing any base classifier as its ensemble members to assemble a powerfully built combinational classifier. Decision-tree classifier and multilayer perceptron classifier as some basic classifiers have been employed in the experiments to indicate the proposed method accomplish higher predictive accuracy compared to meta-learning algorithms like Boosting and Bagging. Furthermore, EBAGTS outperforms Boosting more impressively as the training data set gets broader. It is illustrated that EBAGTS can fulfill better performance comparing to the state of the art.

## 16758. An Augmented Reality Question Answering System Based on Ensemble Neural Networks

- 标题：An Augmented Reality Question Answering System Based on Ensemble Neural Networks
- 作者：Chi‐Hua Chen, Wan Jia Chen, Chi‐Chun Lo, Feng-Jang Hwang
- 年份：2017
- 出版日期：2017-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2017.2743746
- OpenAlex ID：https://openalex.org/W2753700642
- 落地页：https://doi.org/10.1109/access.2017.2743746
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Weighting, Artificial neural network, Artificial intelligence, Class (philosophy), Machine learning, Data mining, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This paper proposes a classification algorithm based on ensemble neural networks. In the training phase, the proposed algorithm uses a random number of training data to develop multiple random artificial neural network (ANN) models until those ANN models converge. Those models with lower accuracy than the threshold are filtered out. The remaining highly accurate models will be used to predict the output in the testing phase. Meanwhile, the accuracy of ANN models is presented as a weighting value in the testing phase. In the testing phase, the testing data are loaded into the selected ANN models to predict the output class. The output values are multiplied by the corresponding weighting values of ANN models. Then the weighted average of the outputs can be obtained. Finally, the predicted output is converted into the predicted class. We design an augmented reality question answering system (AR-QAS) applying and implementing the proposed algorithm on mobile devices. AR-QAS offers an interactive user interface and automatically replies according to user's queries. By comparing with the logistic regression method and the ANN method, the experiment results demonstrate that the proposed algorithm offers the highest accuracy.

## 16759. Red Hen Lab: Dataset and Tools for Multimodal Human Communication Research

- 标题：Red Hen Lab: Dataset and Tools for Multimodal Human Communication Research
- 作者：Jungseock Joo, Francis F. Steen, Mark Turner
- 年份：2017
- 出版日期：2017-09-21
- 类型：article
- 语言：en
- 来源：KI - Künstliche Intelligenz
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0933-1875
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s13218-017-0505-9
- OpenAlex ID：https://openalex.org/W2757693491
- 落地页：https://doi.org/10.1007/s13218-017-0505-9
- 主主题：Speech and dialogue systems
- 主题：Speech and dialogue systems, Robotics and Automated Systems, Multimodal Machine Learning Applications
- 关键词：Multidisciplinary approach, Variety (cybernetics), Computer science, Human–computer interaction, Data science, Artificial intelligence, Sociology, Social science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16760. Adapting Novelty to Classical Planning as Heuristic Search

- 标题：Adapting Novelty to Classical Planning as Heuristic Search
- 作者：Michael Katz, Nir Lipovetzky, Dany Moshkovich, Alexander Tuisov
- 年份：2017
- 出版日期：2017-06-05
- 类型：article
- 语言：en
- 来源：Proceedings of the International Conference on Automated Planning and Scheduling
- 来源类型：journal
- ISSN-L：2334-0835
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1609/icaps.v27i1.13819
- OpenAlex ID：https://openalex.org/W2760525174
- 落地页：https://doi.org/10.1609/icaps.v27i1.13819
- 开放 PDF 链接：https://ojs.aaai.org/index.php/ICAPS/article/download/13819/13668
- 主主题：AI-based Problem Solving and Planning
- 主题：AI-based Problem Solving and Planning, Reservoir Engineering and Simulation Methods, Machine Learning and Algorithms
- 关键词：Novelty, Satisficing, Heuristics, Heuristic, Computer science, State (computer science), Artificial intelligence, Variety (cybernetics), Exploit, Incremental heuristic search, Mathematical optimization, Mathematics, Beam search, Search algorithm, Algorithm, Psychology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The introduction of the concept of state novelty has advanced the state of the art in deterministic online planning in Atari-like problems and in planning with rewards in general, when rewards are defined on states. In classical planning, however, the success of novelty as the dichotomy between novel and non-novel states was somewhat limited. Until very recently, novelty-based methods were not able to successfully compete with state-of-the-art heuristic search based planners. In this work we adapt the concept of novelty to heuristic search planning, defining the novelty of a state with respect to its heuristic estimate. We extend the dichotomy between novel and non-novel states and quantify the novelty degree of state facts. We then show a variety of heuristics based on the concept of novelty and exploit the recently introduced best-first width search for satisficing classical planning. Finally,we empirically show the resulting planners to significantly improve the state of the art in satisficing planning.

## 16761. A unifying analysis for the supervised descriptive rule discovery via the weighted relative accuracy

- 标题：A unifying analysis for the supervised descriptive rule discovery via the weighted relative accuracy
- 作者：C. J. Carmona, María José del Jesús, Francisco Herrera
- 年份：2017
- 出版日期：2017-10-14
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2017.10.015
- OpenAlex ID：https://openalex.org/W2763752391
- 落地页：https://doi.org/10.1016/j.knosys.2017.10.015
- 主主题：Data Mining Algorithms and Applications
- 主题：Data Mining Algorithms and Applications, Machine Learning and Data Classification, Multi-Criteria Decision Making
- 关键词：Computer science, Artificial intelligence, Data mining, Contrast (vision), Descriptive statistics, Property (philosophy), Machine learning, Set (abstract data type), Supervised learning, Quality (philosophy), Mathematics, Statistics, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16762. DATA MINING TECHNIQUE TO ANALYZE SOIL NUTRIENTS BASED ON HYBRID CLASSIFICATION

- 标题：DATA MINING TECHNIQUE TO ANALYZE SOIL NUTRIENTS BASED ON HYBRID CLASSIFICATION
- 作者：E. Manjula
- 年份：2017
- 出版日期：2017-08-30
- 类型：article
- 语言：en
- 来源：International Journal of Advanced Research in Computer Science
- 来源类型：journal
- 出版方：International Journal of Advanced Research in Computer Science
- ISSN-L：0976-5697
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.26483/ijarcs.v8i8.4794
- OpenAlex ID：https://openalex.org/W2766952360
- 落地页：https://doi.org/10.26483/ijarcs.v8i8.4794
- 开放 PDF 链接：http://ijarcs.info/index.php/Ijarcs/article/download/4794/4208
- 主主题：Data Mining Algorithms and Applications
- 主题：Data Mining Algorithms and Applications, Smart Agriculture and AI, Machine Learning and Data Classification
- 关键词：Agriculture, Agricultural engineering, Computer science, Nutrient, Environmental science, Precision agriculture, Database, Chemistry
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Data mining methods are greatly admired in the research field of agriculture. The agriculture factors weather, rain, soil, pesticides and fertilizers are the main responsible aspect to raise the production of yields. The fundamental basic key aspect of agriculture is Soil for crop growing. Examination of soil is a noteworthy part of soil asset management in horticulture. The soil investigation is exceptionally useful for cultivators to discover which sort of harvests to be developed in a specific soil condition. The main target of this work is to investigate soil supplements utilizing data mining classification techniques. A large data set of soil nutrients status database was collected from the Department of Agriculture, Cooperation and Farmers Welfare. The database contains measurement of soil nutrients for all different states. This work takes some district of Tamil Nadu in India to analyze the soil nutrients. Distinctive sort's soil has diverse variety of supplements. This paper chooses Nitrogen, Phosphorus, Potassium, Calcium, Magnesium, Sulfur, Iron, Zinc, and so forth, nutrients for investigating the soil supplements utilizing Naïve Bayes, Decision Tree and Hybrid approach of Naïve Bayes and Decision Tree. The performance of the classification algorithms are compared based on the following two factors: accuracy and execution time.

## 16763. The Role of Consistency in Detecting Deception: The Superiority of Correspondence over Coherence

- 标题：The Role of Consistency in Detecting Deception: The Superiority of Correspondence over Coherence
- 作者：J. Pete Blair, Torsten Reimer, Timothy R. Levine
- 年份：2018
- 出版日期：2018-03-20
- 类型：article
- 语言：en
- 来源：Communication Studies
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：1051-0974
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1080/10510974.2018.1447492
- OpenAlex ID：https://openalex.org/W2792416779
- 落地页：https://doi.org/10.1080/10510974.2018.1447492
- 主主题：Deception detection and forensic psychology
- 主题：Deception detection and forensic psychology, Psychopathy, Forensic Psychiatry, Sexual Offending, Adversarial Robustness in Machine Learning
- 关键词：Deception, Coherence (philosophical gambling strategy), Consistency (knowledge bases), Conceptualization, Psychology, Epistemology, Social psychology, Synchronicity, Cognitive psychology, Computer science, Artificial intelligence, Mathematics, Philosophy, Psychoanalysis, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Inconsistency is often considered an indication of deceit. The conceptualization of consistency used in deception research, however, has not made a clear distinction between two concepts long differentiated by philosophers: coherence and correspondence. The existing literature suggests that coherence is not generally useful for deception detection. Correspondence, however, appears to be quite useful. The present research developed a model of how correspondence is utilized to make judgments, and this article reports on four studies designed to elaborate on the model. The results suggest that judges attend strongly to correspondence and that they do so in an additive fashion. As noncorrespondent information accumulates, an increasingly smaller proportion of judges make truthful assessments of guilty suspects. This work provides a basic framework for examining how information is utilized to make deception judgments and forms the correspondence and coherence module of truth-default theory.

## 16764. Biometric surveillance using visual question answering

- 标题：Biometric surveillance using visual question answering
- 作者：Andeep S. Toor, Harry Wechsler, Michele Nappi
- 年份：2018
- 出版日期：2018-02-22
- 类型：article
- 语言：en
- 来源：Pattern Recognition Letters
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-8655
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patrec.2018.02.013
- OpenAlex ID：https://openalex.org/W2793127982
- 落地页：https://doi.org/10.1016/j.patrec.2018.02.013
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Biometrics, Relevance (law), Leverage (statistics), Triage, Artificial intelligence, Context (archaeology), Machine learning, Human–computer interaction, Information retrieval, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16765. Text2Video: An End-to-end Learning Framework for Expressing Text With Videos

- 标题：Text2Video: An End-to-end Learning Framework for Expressing Text With Videos
- 作者：Xiaoshan Yang, Tianzhu Zhang, Changsheng Xu
- 年份：2018
- 出版日期：2018-02-26
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2018.2807588
- OpenAlex ID：https://openalex.org/W2793476612
- 落地页：https://doi.org/10.1109/tmm.2018.2807588
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Video Analysis and Summarization, Human Pose and Action Recognition
- 关键词：Computer science, Sentence, Consistency (knowledge bases), Task (project management), Artificial intelligence, Video production, Exploit, Deep learning, Sequence (biology), Information retrieval, End-to-end principle, Natural language processing, Machine learning, Multimedia
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Video creation is a challenging and highly profession-al task that generally involves substantial manual efforts. To ease this burden, a better approach is to automatically produce new videos based on clips from the massive amount of existing videos according to arbitrary text. In this paper, we formulate video creation as a problem of retrieving a sequence of videos for a sentence stream. To achieve this goal, we propose a novel multimodal recurrent architecture for automatic video production. Compared with existing methods, the proposed model has three major advantages. First, it is the first completely integrated end-to-end deep learning system for real-world production to the best of our knowledge. We are among the first to address the problem of retrieving a sequence of videos for a sentence stream. Second, it can effectively exploit the correspondence between sentences and video clips through semantic consistency modeling. Third, it can model the visual coherence well by requiring that the produced videos should be organized coherently in terms of visual appearance. We have conducted extensive experiments on two applications, including video retrieval and video composition. The qualitative and quantitative results obtained on two public datasets used in the Large Scale Movie Description Challenge 2016 both demonstrate the effectiveness of the proposed model compared with other state-of-the-art algorithms.

## 16766. CBR-PSO: cost-based rough particle swarm optimization approach for high-dimensional imbalanced problems

- 标题：CBR-PSO: cost-based rough particle swarm optimization approach for high-dimensional imbalanced problems
- 作者：Emel Kızılkaya Aydoğan, Mihrimah Özmen, Yılmaz Delice
- 年份：2018
- 出版日期：2018-04-02
- 类型：article
- 语言：en
- 来源：Neural Computing and Applications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0941-0643
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00521-018-3469-2
- OpenAlex ID：https://openalex.org/W2796317257
- 落地页：https://doi.org/10.1007/s00521-018-3469-2
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Rough Sets and Fuzzy Logic, Machine Learning and Data Classification
- 关键词：Particle swarm optimization, Computer science, Robustness (evolution), Data mining, Rough set, Reduction (mathematics), Computational Science and Engineering, Machine learning, Artificial intelligence, Pattern recognition (psychology), Mathematical optimization, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16767. A correlation-based binary particle swarm optimization method for feature selection in human activity recognition

- 标题：A correlation-based binary particle swarm optimization method for feature selection in human activity recognition
- 作者：Huaijun Wang, Ruomeng Ke, Junhuai Li, Yang An, Kan Wang, Yu Lei
- 年份：2018
- 出版日期：2018-04-01
- 类型：article
- 语言：en
- 来源：International Journal of Distributed Sensor Networks
- 来源类型：journal
- 出版方：Hindawi Publishing Corporation
- ISSN-L：1550-1329
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1177/1550147718772785
- OpenAlex ID：https://openalex.org/W2801221325
- 落地页：https://doi.org/10.1177/1550147718772785
- 开放 PDF 链接：https://journals.sagepub.com/doi/pdf/10.1177/1550147718772785
- 主主题：Context-Aware Activity Recognition Systems
- 主题：Context-Aware Activity Recognition Systems, Human Pose and Action Recognition, Machine Learning and Data Classification
- 关键词：Feature selection, Particle swarm optimization, Computer science, Artificial intelligence, Pattern recognition (psychology), Feature (linguistics), Support vector machine, k-nearest neighbors algorithm, Fitness function, Perceptron, Random forest, Multi-swarm optimization, C4.5 algorithm, Metaheuristic, Feature vector, Naive Bayes classifier, Machine learning, Genetic algorithm, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Effective feature selection determines the efficiency and accuracy of a learning process, which is essential in human activity recognition. In existing works, for simplification purposes, feature selection algorithms are mostly based on the assumption of feature independence. However, in some scenarios, the optimization method based on this independence hypothesis results in poor recognition performance. This article proposes a correlation-based binary particle swarm optimization method for feature selection in human activity recognition. In the proposed algorithm, the particle swarm optimization algorithm is no longer used as a black box. Meanwhile, correlation coefficients among the features are added to binary particle swarm optimization as a feature correlation factor to determine the position of particles, so that the feature with more information is more likely to be selected. The k-nearest neighbor classifier is then used as the fitness function in the particle swarm optimization to evaluate the performance of the feature subset, that is, feature combination with the highest k-nearest neighbor classifier recognition rate would be picked as the eigenvector. Experimental results show that the proposed method can work well with six classifiers, namely, J48, random forest, k-nearest neighbor, multilayer perceptron, naïve Bayesian, and support vector machine, and the new algorithm can improve the classification accuracy in the OPPORTUNITY Activity Recognition dataset.

## 16768. Hybrid Ensemble Framework for Heart Disease Detection and Prediction

- 标题：Hybrid Ensemble Framework for Heart Disease Detection and Prediction
- 作者：Elham Nikookar, Ebrahim Naderi
- 年份：2018
- 出版日期：2018-01-01
- 类型：article
- 语言：en
- 来源：International Journal of Advanced Computer Science and Applications
- 来源类型：journal
- 出版方：Science and Information Organization
- ISSN-L：2156-5570
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.14569/ijacsa.2018.090533
- OpenAlex ID：https://openalex.org/W2805567688
- 落地页：https://doi.org/10.14569/ijacsa.2018.090533
- 开放 PDF 链接：http://thesai.org/Downloads/Volume9No5/Paper_33-Hybrid_Ensemble_Framework_for_Heart_Disease.pdf
- 主主题：Artificial Intelligence in Healthcare
- 主题：Artificial Intelligence in Healthcare, Imbalanced Data Classification Techniques, Machine Learning and Data Classification
- 关键词：Computer science, Ensemble forecasting, Ensemble learning, Heart disease, Machine learning, Artificial intelligence, Data mining, Decision support system, Medicine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Data mining techniques have been widely used in clinical decision support systems for detection and prediction of various diseases. As heart disease is the leading cause of death for both men and women, detection and prediction of the heart disease is one of the most important issues in medical domain and many researchers developed intelligent medical decision support systems to improve the ability of the CAD systems in diagnosing heart disease. However, there are almost no studies investigating capabilities of hybrid ensemble methods in building a detection and prediction model for heart disease. In this work, we investigate the use of hybrid ensemble model in which a more reliable ensemble than basic ensemble models is proposed and leads to better performance than other heart disease prediction models. To evaluate the performance of proposed model, a dataset containing 278 samples from SPECT heart disease database is used that after applying the model on the data, 96% of classification accuracy, 80% of sensitivity and 93% of specificity are obtained that indicates acceptable performance of the proposed hybrid ensemble model in comparison with basic ensemble model as well as other state of the art models.

## 16769. Modeling visual and word-conditional semantic attention for image captioning

- 标题：Modeling visual and word-conditional semantic attention for image captioning
- 作者：Chunlei Wu, Yiwei Wei, Xiaoliang Chu, Fei Su, Leiquan Wang
- 年份：2018
- 出版日期：2018-06-15
- 类型：article
- 语言：en
- 来源：Signal Processing Image Communication
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0923-5965
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.image.2018.06.002
- OpenAlex ID：https://openalex.org/W2808468291
- 落地页：https://doi.org/10.1016/j.image.2018.06.002
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Closed captioning, Computer science, Word (group theory), Artificial intelligence, Image (mathematics), Natural language processing, Semantics (computer science), Dual (grammatical number), Speech recognition, Modal, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16770. General Value Function Networks

- 标题：General Value Function Networks
- 作者：Matthew Schlegel, Andrew Jacobsen, Zaheer Abbas, Andrew Patterson, Adam White, Martha White
- 年份：2021
- 出版日期：2021-01-28
- 类型：article
- 语言：en
- 来源：Journal of Artificial Intelligence Research
- 来源类型：journal
- 出版方：AI Access Foundation
- ISSN-L：1076-9757
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1613/jair.1.12105
- OpenAlex ID：https://openalex.org/W2884092934
- 落地页：https://doi.org/10.1613/jair.1.12105
- 开放 PDF 链接：https://jair.org/index.php/jair/article/download/12105/26653
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Explainable Artificial Intelligence (XAI), Adversarial Robustness in Machine Learning
- 关键词：Recurrent neural network, Computer science, Function (biology), Truncation (statistics), State (computer science), Observable, Artificial intelligence, Construct (python library), Domain (mathematical analysis), Machine learning, Algorithm, Artificial neural network, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
State construction is important for learning in partially observable environments. A general purpose strategy for state construction is to learn the state update using a Recurrent Neural Network (RNN), which updates the internal state using the current internal state and the most recent observation. This internal state provides a summary of the observed sequence, to facilitate accurate predictions and decision-making. At the same time, specifying and training RNNs is notoriously tricky, particularly as the common strategy to approximate gradients back in time, called truncated Back-prop Through Time (BPTT), can be sensitive to the truncation window. Further, domain-expertise—which can usually help constrain the function class and so improve trainability—can be difficult to incorporate into complex recurrent units used within RNNs. In this work, we explore how to use multi-step predictions to constrain the RNN and incorporate prior knowledge. In particular, we revisit the idea of using predictions to construct state and ask: does constraining (parts of) the state to consist of predictions about the future improve RNN trainability? We formulate a novel RNN architecture, called a General Value Function Network (GVFN), where each internal state component corresponds to a prediction about the future represented as a value function. We first provide an objective for optimizing GVFNs, and derive several algorithms to optimize this objective. We then show that GVFNs are more robust to the truncation level, in many cases only requiring one-step gradient updates.

## 16771. Reinforcement-based Method for Simultaneous Clustering Algorithm Selection and its Hyperparameters Optimization

- 标题：Reinforcement-based Method for Simultaneous Clustering Algorithm Selection and its Hyperparameters Optimization
- 作者：Viacheslav Shalamov, Valeria Efimova, Sergey Muravyov, Andrey Filchenkov
- 年份：2018
- 出版日期：2018-01-01
- 类型：article
- 语言：en
- 来源：Procedia Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1877-0509
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.1016/j.procs.2018.08.247
- OpenAlex ID：https://openalex.org/W2893113437
- 落地页：https://doi.org/10.1016/j.procs.2018.08.247
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Machine Learning and Data Classification, Advanced Multi-Objective Optimization Algorithms
- 关键词：Hyperparameter, Cluster analysis, Computer science, Reinforcement learning, Hyperparameter optimization, Machine learning, Artificial intelligence, Selection (genetic algorithm), Algorithm, Support vector machine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A wide range of clustering algorithms exists, most of them expose many hyperparameters, on which clustering partition quality depends. Simultaneous algorithm (model) selection and its hyperparameters optimization is considered to be a sophisticated task, which is known according to some sources as combined algorithm selection and hyperparameter optimization. In this paper, we focus on problem of selecting a clustering algorithm and its hyperparameter vector simultaneously given a dataset in order to achieve the best partition quality. We propose a method for selecting a proper clustering algorithm and its hyperparameter vector using reinforcement learning. Instead of tuning hyperparameters for all available clustering algorithms and selecting one showing the best performance, we make them to compete for time that they can use for optimizing their own hyperparameters. In our algorithm, we use a framework for multi-armed bandit problem, which is a special case of reinforcement learning. Each clustering algorithm is considered as an arm in the multi-armed bandit setting, while assigning a time budget to optimize hyperparameters of a clustering algorithm is considered as playing the corresponding arm. We conducted series of experiments for comparing out reinforcement learning approach to the classical exhaustive search approach. We conducted experiments on 20 datasets from UCI Repository such as Iris, haberman, krvskp, glass and other. We use 19 cluster validity indices to validate the clusters, built by selected and configured algorithm. As a hyperparameter optimization algorithm, we used SMAC. Our approach managed to improve model selection and hyperparameter optimization process, by sustaining the exploration-exploitation trade-off and spending available time budget more wisely.

## 16772. Three Types of Producer's and Consumer's Risks in the Single Sampling Plan

- 标题：Three Types of Producer's and Consumer's Risks in the Single Sampling Plan
- 作者：Young H. Chun, Dan B. Rinks
- 年份：1998
- 出版日期：1998-07-01
- 类型：article
- 语言：en
- 来源：Journal of Quality Technology
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0022-4065
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1080/00224065.1998.11979854
- OpenAlex ID：https://openalex.org/W28945407
- 落地页：https://doi.org/10.1080/00224065.1998.11979854
- 主主题：Distributed Sensor Networks and Detection Algorithms
- 主题：Distributed Sensor Networks and Detection Algorithms, Advanced Statistical Process Monitoring, Machine Learning and Algorithms
- 关键词：Acceptance sampling, Bayes' theorem, Sampling (signal processing), Statistics, Focus (optics), Econometrics, Mathematics, Actuarial science, Computer science, Economics, Bayesian probability, Sample size determination
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The classical producer's risk and the classical consumer's risk are defined in acceptance sampling based on the assumption that the proportion defective of incoming lots is a constant. This assumption has been a focus of much of the criticism of acceptance sampling in recent years. In this paper, we assume that the proportion defective is a random variable that follows a beta distribution, and we derive the modified producer's risk and the modified consumer's risk. We also derive the Bayes producer's risk and the Bayes consumer's risk. In addition, we clarify the relationships of the modified and Bayes risks with the classical risks.

## 16773. Tractable Sampling Strategies for Ordinal Optimization

- 标题：Tractable Sampling Strategies for Ordinal Optimization
- 作者：Dong-wook Shin, Mark Broadie, Assaf Zeevi
- 年份：2018
- 出版日期：2018-11-01
- 类型：article
- 语言：en
- 来源：Operations Research
- 来源类型：journal
- 出版方：Institute for Operations Research and the Management Sciences
- ISSN-L：0030-364X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1287/opre.2018.1753
- OpenAlex ID：https://openalex.org/W2900615677
- 落地页：https://doi.org/10.1287/opre.2018.1753
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Advanced Bandit Algorithms Research, Auction Theory and Applications
- 关键词：Ordinal optimization, Sampling (signal processing), Benchmark (surveying), Mathematical optimization, Computer science, Set (abstract data type), Optimization problem, Finite set, Time horizon, Horizon, Ordinal data, Mathematics, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In “Tractable Sampling Strategies for Ordinal Optimization,” D. Shin, M. Broadie, and A. Zeevi analyze a problem of ordinal optimization where the objective is to select the best of several competing systems, when the probability distributions governing each system’s performance are not known but can be learned via sampling. The objective is to dynamically allocate samples within a finite sampling budget to maximize the likelihood of identifying the best system. An exact solution to this problem over any finite time horizon is difficult to characterize. In lieu of that, we introduce a family of practically implementable sampling policies and characterize the set of problem instances over which their performance (over a long time horizon) is essentially the best possible. Furthermore, we show via numerical testing that the proposed policies perform well compared with other benchmark policies over finite time horizons.

## 16774. Random Untargeted Adversarial Example on Deep Neural Network

- 标题：Random Untargeted Adversarial Example on Deep Neural Network
- 作者：Hyun Kwon, Yongchul Kim, Hyunsoo Yoon, Daeseon Choi
- 年份：2018
- 出版日期：2018-12-10
- 类型：article
- 语言：en
- 来源：Symmetry
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2073-8994
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/sym10120738
- OpenAlex ID：https://openalex.org/W2904294250
- 落地页：https://doi.org/10.3390/sym10120738
- 开放 PDF 链接：https://www.mdpi.com/2073-8994/10/12/738/pdf?version=1545130619
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Integrated Circuits and Semiconductor Failure Analysis, Advanced Malware Detection Techniques
- 关键词：Adversarial system, Computer science, MNIST database, Artificial intelligence, Scheme (mathematics), Distortion (music), Class (philosophy), Machine learning, Pattern recognition (psychology), Artificial neural network, Deep learning, Embedding, Vulnerability (computing), Computer security, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep neural networks (DNNs) have demonstrated remarkable performance in machine learning areas such as image recognition, speech recognition, intrusion detection, and pattern analysis. However, it has been revealed that DNNs have weaknesses in the face of adversarial examples, which are created by adding a little noise to an original sample to cause misclassification by the DNN. Such adversarial examples can lead to fatal accidents in applications such as autonomous vehicles and disease diagnostics. Thus, the generation of adversarial examples has attracted extensive research attention recently. An adversarial example is categorized as targeted or untargeted. In this paper, we focus on the untargeted adversarial example scenario because it has a faster learning time and less distortion compared with the targeted adversarial example. However, there is a pattern vulnerability with untargeted adversarial examples: Because of the similarity between the original class and certain specific classes, it may be possible for the defending system to determine the original class by analyzing the output classes of the untargeted adversarial examples. To overcome this problem, we propose a new method for generating untargeted adversarial examples, one that uses an arbitrary class in the generation process. Moreover, we show that our proposed scheme can be applied to steganography. Through experiments, we show that our proposed scheme can achieve a 100% attack success rate with minimum distortion (1.99 and 42.32 using the MNIST and CIFAR10 datasets, respectively) and without the pattern vulnerability. Using a steganography test, we show that our proposed scheme can be used to fool humans, as demonstrated by the probability of their detecting hidden classes being equal to that of random selection.

## 16775. An Asymptotic Ensemble Learning Framework for Big Data Analysis

- 标题：An Asymptotic Ensemble Learning Framework for Big Data Analysis
- 作者：Salman Salloum, Joshua Zhexue Huang, Yulin He, Xiaojun Chen
- 年份：2018
- 出版日期：2018-12-24
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2018.2889355
- OpenAlex ID：https://openalex.org/W2906300927
- 落地页：https://doi.org/10.1109/access.2018.2889355
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/8600701/08586790.pdf
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Neural Networks and Applications, Machine Learning and Data Classification
- 关键词：Computer science, Big data, Block (permutation group theory), Data set, Data mining, Set (abstract data type), Distributed File System, Partition (number theory), Sample (material), Data modeling, Algorithm, Database, Mathematics, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In order to enable big data analysis when data volume goes beyond the available computing resources, we propose a new method for big data analysis. This method uses only a few random sample data blocks of a big data set to obtain approximate results for the entire data set. The random sample partition (RSP) distributed data model is used to represent a big data set as a set of non-overlapping random sample data blocks. Each block is saved as an RSP data block file that can be used directly to estimate the statistical properties of the entire data set. A subset of RSP data blocks is randomly selected and analyzed with existing sequential algorithms in parallel. Then, the results from these blocks are combined to obtain ensemble estimates and models which can be improved gradually by appending new results from the newly analyzed RSP data blocks. To this end, we propose a distributed data-parallel framework (Alpha framework) and develop a prototype of this framework using Microsoft R Server packages and Hadoop distributed file system. The experimental results of three real data sets show that a subset of RSP data blocks of a data set is sufficient to obtain estimates and models which are equivalent to those computed from the entire data set.

## 16776. Primality testing with Gaussian periods

- 标题：Primality testing with Gaussian periods
- 作者：Hendrik W. Lenstra, Carl Pomerance
- 年份：2019
- 出版日期：2019-01-08
- 类型：article
- 语言：en
- 来源：Journal of the European Mathematical Society
- 来源类型：journal
- 出版方：European Mathematical Society
- ISSN-L：1435-9855
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.4171/jems/861
- OpenAlex ID：https://openalex.org/W2908533878
- 落地页：https://doi.org/10.4171/jems/861
- 主主题：Algorithms and Data Compression
- 主题：Algorithms and Data Compression, Machine Learning and Algorithms, Statistical Methods in Clinical Trials
- 关键词：Primality test, Mathematics, Gaussian, Combinatorics, Prime (order theory)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We exhibit a deterministic algorithm that, for some effectively computable real number c , decides whether a given integer n &gt; 1 is prime within time \mathrm {log} n)^6\cdot(2+\mathrm {log\log} n)^c . The same result, with 21/2 in place of 6 , was proved by Agrawal, Kayal, and Saxena. Our algorithm follows the same pattern as theirs, performing computations in an auxiliary ring extension of \mathbb Z/n\mathbb Z . We allow our rings to be generated by Gaussian periods rather than by roots of unity, which leaves us greater freedom in the selection of the auxiliary parameters and enables us to obtain a better run time estimate. The proof depends on results in analytic number theory and on the following theorem from additive number theory, which was provided by D. Bleichenbacher: if t is a real number with 0 &lt; t \le1 , and S is an open subset of the interval (0,t) with \int_S\mathrm d x/x &gt; t , then each real number greater than or equal to 1 is in the additive semigroup generated by S . A byproduct of our main result is an improved algorithm for constructing finite fields of given characteristic and approximately given degree.

## 16777. Semantic Relational Object Tracking

- 标题：Semantic Relational Object Tracking
- 作者：Andreas Persson, Pedro Zuidberg Dos Martires, Luc De Raedt, Amy Loutfi
- 年份：2019
- 出版日期：2019-10-03
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Cognitive and Developmental Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2379-8920
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1109/tcds.2019.2915763
- OpenAlex ID：https://openalex.org/W2917101430
- 落地页：https://doi.org/10.1109/tcds.2019.2915763
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/7274989/9032076/08744391.pdf
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Video Surveillance and Tracking Methods
- 关键词：Probabilistic logic, Object (grammar), Matching (statistics), Set (abstract data type), Anchoring, Cognitive neuroscience of visual object recognition, Semantics (computer science), Video tracking, Perception
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This paper addresses the topic of semantic world modeling by conjoining probabilistic reasoning and object anchoring. The proposed approach uses a so-called bottom-up object anchoring method that relies on rich continuous attribute values measured from perceptual sensor data. A novel anchoring matching function learns to maintain object entities in space and time and is validated using a large set of trained humanly annotated ground truth data of real-world objects. For more complex scenarios, a high-level probabilistic object tracker has been integrated with the anchoring framework and handles the tracking of occluded objects via reasoning about the state of unobserved objects. We demonstrate the performance of our integrated approach through scenarios such as the shell game scenario, where we illustrate how anchored objects are retained by preserving relations through probabilistic reasoning.

## 16778. Improving transparency of deep neural inference process

- 标题：Improving transparency of deep neural inference process
- 作者：Hiroshi Kuwajima, Masayuki Tanaka, Masatoshi Okutomi
- 年份：2019
- 出版日期：2019-04-12
- 类型：article
- 语言：en
- 来源：Progress in Artificial Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：2192-6352
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s13748-019-00179-x
- OpenAlex ID：https://openalex.org/W2921105605
- 落地页：https://doi.org/10.1007/s13748-019-00179-x
- 主主题：Explainable Artificial Intelligence (XAI)
- 主题：Explainable Artificial Intelligence (XAI), Adversarial Robustness in Machine Learning, Machine Learning and Data Classification
- 关键词：Computer science, Inference, Transparency (behavior), Consistency (knowledge bases), Artificial intelligence, Black box, Artificial neural network, Machine learning, Process (computing), Feature (linguistics), Deep learning, Data mining, Natural language processing
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16779. Learning to Learn: Hierarchical Meta-Critic Networks

- 标题：Learning to Learn: Hierarchical Meta-Critic Networks
- 作者：Zhixiong Xu, Lei Cao, Xiliang Chen
- 年份：2019
- 出版日期：2019-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2019.2914469
- OpenAlex ID：https://openalex.org/W2942925444
- 落地页：https://doi.org/10.1109/access.2019.2914469
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/8600701/08704874.pdf
- 主主题：Reinforcement Learning in Robotics
- 主题：Reinforcement Learning in Robotics, Adaptive Dynamic Programming Control, Adversarial Robustness in Machine Learning
- 关键词：Reinforcement learning, Computer science, Artificial intelligence, Task (project management), Meta learning (computer science), Machine learning, Robotics, Control (management), Sample (material), Robot
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In recent years, deep reinforcement learning methods have achieved impressive performance in many different fields, including playing games, robotics, and dialogue systems. However, there are still a lot of restrictions here, one of which is the demand for massive amounts of sampled data. In this paper, a hierarchical meta-learning method based on the actor-critic algorithm is proposed for sample efficient learning. This method provides the transferable knowledge that can efficiently train an actor on a new task with a few trials. Specifically, a global basic critic, meta critic, and task specified network are shared within a distribution of tasks and are capable of criticizing any actor trying to solve any specified task. The hierarchical framework is applied to a critic network in the actor-critic algorithm for distilling meta-knowledge above the task level and addressing distinct tasks. The proposed method is evaluated on multiple classic control tasks with reinforcement learning algorithms, including the start-of-the-art meta-learning methods. The experimental results statistically demonstrate that the proposed method achieves state-of-the-art performance and attains better results with more depth of meta critic network.

## 16780. Rademacher dropout: An adaptive dropout for deep neural network via optimizing generalization gap

- 标题：Rademacher dropout: An adaptive dropout for deep neural network via optimizing generalization gap
- 作者：Haotian Wang, Wenjing Yang, Zhenyu Zhao, Tingjin Luo, Ji Wang, Yuhua Tang
- 年份：2019
- 出版日期：2019-05-11
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2019.05.008
- OpenAlex ID：https://openalex.org/W2944145193
- 落地页：https://doi.org/10.1016/j.neucom.2019.05.008
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Domain Adaptation and Few-Shot Learning, Machine Learning and Data Classification
- 关键词：Dropout (neural networks), Computer science, Benchmark (surveying), Generalization, Constraint (computer-aided design), Artificial neural network, Convergence (economics), Artificial intelligence, Mathematical optimization, Machine learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16781. Robust Pervasive Detection for Adversarial Samples of Artificial Intelligence in IoT Environments

- 标题：Robust Pervasive Detection for Adversarial Samples of Artificial Intelligence in IoT Environments
- 作者：Shen Wang, Zhuobiao Qiao
- 年份：2019
- 出版日期：2019-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2019.2919695
- OpenAlex ID：https://openalex.org/W2947696371
- 落地页：https://doi.org/10.1109/access.2019.2919695
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/8600701/08725605.pdf
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Bacillus and Francisella bacterial research
- 关键词：Computer science, MNIST database, Robustness (evolution), Artificial intelligence, Adversarial system, Artificial neural network, Internet of Things, Deep neural networks, Machine learning, Classifier (UML), Scheme (mathematics), Pattern recognition (psychology), Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Nowadays, artificial intelligence technologies (e.g., deep neural networks) have been used widely in the Internet of Things (IoT) to provide smart services and sensing data processing. The evolving neural network even exceeds the human cognitive level. However, the accuracy of these structures depends to some extent on the accuracy of the training data. Some well-designed generated antagonistic disturbances are sufficient to deceive model when added to images. Such attacks cause the classifiers trained by the neural network to misidentify the object and thus completely fail. On the other hand, the various existing defensive methods that have been proposed suffer from two criticisms. The first thing that bears the brunt is unsatisfactory detection rate due to low robustness toward the adversarial sample. Second, the excessive dependence on the output of specific network structure layers hinders the emergence of universal schemes. In this paper, we propose the large margin cosine estimation (LMCE) detection scheme to overcome the above shortcomings, making the detection independent and universal. We illustrate the principle of our approach and demonstrate the significance and analysis of some important parameters. Moreover, we model various types of adversarial attacks and establish proposed defense mechanisms against them and evaluate our approach from different aspects. This method has been clearly validated on a range of standard datasets including MNIST, CIFAR-10, and SVHN. The assessment strongly reflects the robustness and pervasive of this approach in the face of various white and semi-white box attacks.

## 16782. Decision tree for modeling survival data with competing risks

- 标题：Decision tree for modeling survival data with competing risks
- 作者：Kazeem A. Dauda, Biswabrata Pradhan, B. Uma Shankar, Sushmita Mitra
- 年份：2019
- 出版日期：2019-06-04
- 类型：article
- 语言：en
- 来源：Journal of Applied Biomedicine
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0208-5216
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.bbe.2019.05.001
- OpenAlex ID：https://openalex.org/W2948284875
- 落地页：https://doi.org/10.1016/j.bbe.2019.05.001
- 主主题：Statistical Methods and Inference
- 主题：Statistical Methods and Inference, Data Mining Algorithms and Applications, Machine Learning and Data Classification
- 关键词：Decision tree, Cart, Computer science, Decision tree learning, Regression, Regression analysis, Tree (set theory), Data mining, Statistics, Recursive partitioning, Machine learning, Artificial intelligence, Mathematics, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16783. Early Stopping for Kernel Boosting Algorithms: A General Analysis With Localized Complexities

- 标题：Early Stopping for Kernel Boosting Algorithms: A General Analysis With Localized Complexities
- 作者：Yuting Wei, Fanny Yang, Martin J. Wainwright
- 年份：2019
- 出版日期：2019-07-09
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tit.2019.2927563
- OpenAlex ID：https://openalex.org/W2961238573
- 落地页：https://doi.org/10.1109/tit.2019.2927563
- 主主题：Statistical Methods and Inference
- 主题：Statistical Methods and Inference, Sparse and Compressive Sensing Techniques, Machine Learning and Algorithms
- 关键词：Boosting (machine learning), AdaBoost, Early stopping, Algorithm, Regularization (linguistics), Estimator, Mathematics, Gaussian, Kernel (algebra), Computer science, Artificial intelligence, Mathematical optimization, Discrete mathematics, Support vector machine, Statistics, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Early stopping of iterative algorithms is a widely used form of regularization in statistics, commonly used in conjunction with boosting and related gradient-type algorithms. Although consistency results have been established in some settings, such estimators are less well-understood than their analogues based on penalized regularization. In this paper, for a relatively broad class of loss functions and boosting algorithms (including L <sup xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">2</sup> -boost, LogitBoost, and AdaBoost, among others), we exhibit a direct connection between the performance of a stopped iterate and the localized Gaussian complexity of the associated function class. This connection allows us to show that the local fixed point analysis of Gaussian or Rademacher complexities, now standard in the analysis of penalized estimators, can be used to derive optimal stopping rules. We derive such stopping rules in detail for various kernel classes and illustrate the correspondence of our theory with practice for Sobolev kernel classes.

## 16784. A Feasible Active Set Method with Reoptimization for Convex Quadratic Mixed-Integer Programming

- 标题：A Feasible Active Set Method with Reoptimization for Convex Quadratic Mixed-Integer Programming
- 作者：Christoph Buchheim, Marianna De Santis, Stefano Lucidi, Francesco Rinaldi, Long Trieu
- 年份：2016
- 出版日期：2016-01-01
- 类型：article
- 语言：en
- 来源：SIAM Journal on Optimization
- 来源类型：journal
- 出版方：Society for Industrial and Applied Mathematics
- ISSN-L：1052-6234
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1137/140978971
- OpenAlex ID：https://openalex.org/W2962794963
- 落地页：https://doi.org/10.1137/140978971
- 主主题：Advanced Optimization Algorithms Research
- 主题：Advanced Optimization Algorithms Research, Machine Learning and Algorithms, Formal Methods in Verification
- 关键词：Quadratic programming, Integer programming, Branch and bound, Solver, Mathematics, Preprocessor, Mathematical optimization, Linear programming, Active set method, Quadratic equation, Integer (computer science), Branch and cut, Branch and price, Set (abstract data type), Feasible region, Regular polygon, Convex optimization, Computer science, Nonlinear programming, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We propose a feasible active set method for convex quadratic programming problems with nonnegativity constraints. This method is specifically designed to be embedded into a branch-and-bound algorithm for convex quadratic mixed- integer programming problems. The branch-and-bound algorithm generalizes the approach for unconstrained convex quadratic integer programming proposed by Buchheim, Caprara, and Lodi [Math. Program., 135 (2012), pp. 369--395] to the presence of linear constraints. The main feature of the latter approach consists of a sophisticated preprocessing phase, leading to a fast enumeration of the branch-and-bound nodes. Moreover, the feasible active set method takes advantage of this preprocessing phase and is well suited for reoptimization. Experimental results for randomly generated instances show that the new approach significantly outperforms the MIQP solver of \tt CPLEX 12.6 for instances with a small number of constraints.

## 16785. Fuzzy-multidimensional deep learning for efficient prediction of patient response to antiretroviral therapy

- 标题：Fuzzy-multidimensional deep learning for efficient prediction of patient response to antiretroviral therapy
- 作者：Moses E. Ekpenyong, Philip I. Etebong, Tenderwealth Clement Jackson
- 年份：2019
- 出版日期：2019-07-01
- 类型：article
- 语言：en
- 来源：Heliyon
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2405-8440
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1016/j.heliyon.2019.e02080
- OpenAlex ID：https://openalex.org/W2962800573
- 落地页：https://doi.org/10.1016/j.heliyon.2019.e02080
- 主主题：HIV Research and Treatment
- 主题：HIV Research and Treatment, Machine Learning and Algorithms, Hepatitis C virus research
- 关键词：Viral load, Machine learning, Fuzzy logic, Artificial intelligence, Human immunodeficiency virus (HIV), Database, Artificial neural network, Medicine, Computer science, Family medicine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Drug component interactions are most likely to trigger unexpected pharmacological effects with unknown causal mechanisms, hence, demanding the discovery of patterns to establish suitable and effective regimens. This paper proposes a novel framework that embeds machine learning (ML) and multidimensional scaling (MDS) techniques, for efficient prediction of patient response to antiretroviral therapy (ART). To achieve this, experiment databases were created from two independent sources: a publicly available HIV domain datasets of patients with failed treatment - hosted by the Stanford University, hereinafter referred to as the Stanford HIV database, and locally sourced datasets gathered from 13 prominent healthcare facilities treating HIV patients in Akwa Ibom State of Nigeria, hereinafter referred to as the Akwa-Ibom HIV database: with 5,780 and 3,168 individual treatment change episodes (TCEs) of HIV treatment indicators (baseline CD4 count (BCD4), followup CD4 count (FCD4), baseline viral load (BRNA), followup viral load (FRNA), and drug type combination (DType)), observed from 1,521 and 1,301 unique patient records, respectively. A hybridised (two-stage) classification system consuming the Interval Type-2 Fuzzy Logic (IT2FL) and Deep Neural Network (DNN) was employed to model and optimise patients' response to ART with appreciable error pruning achieved through MDS. Visualisation of the experiment databases showed remarkable immunological changes in the Akwa-Ibom HIV database, as the FCD4 of TCEs clustered far above the BCD4, compared to the Stanford HIV database, where over 40% of FCD4 clustered below the BCD4. Similar changes were noticed for the RNA, as more FRNA copies clustered below the BRNA for the Akwa-Ibom datasets, compared to the Stamford datasets. DNN classification results for both databases showed best performance metrics for the Levenberg-Marquardt algorithm when compared with the resilient backpropagation algorithm, with improved drug pattern predictions for experiment with MDS. This paper is most likely to evolve an avenue that triggers interesting combination(s) for optimum patient response, while ensuring minimal side effects, as further findings revealed the superiority of the proposed approach over existing approaches.

## 16786. Reducing the Dependence of the Neural Network Function to Systematic Uncertainties in the Input Space

- 标题：Reducing the Dependence of the Neural Network Function to Systematic Uncertainties in the Input Space
- 作者：Stefan Wunsch, Simon Jörger, Roger Wolf, Günter Quast
- 年份：2020
- 出版日期：2020-02-23
- 类型：article
- 语言：en
- 来源：Computing and Software for Big Science
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：2510-2036
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s41781-020-00037-9
- OpenAlex ID：https://openalex.org/W2966648307
- 落地页：https://doi.org/10.1007/s41781-020-00037-9
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s41781-020-00037-9.pdf
- 主主题：Model Reduction and Neural Networks
- 主题：Model Reduction and Neural Networks, Particle physics theoretical and experimental studies, Adversarial Robustness in Machine Learning
- 关键词：Artificial neural network, Stochastic neural network, Function (biology), Simple (philosophy), Time delay neural network, Space (punctuation), Probabilistic neural network, Types of artificial neural networks
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Applications of neural networks to data analyses in natural sciences are complicated by the fact that many inputs are subject to systematic uncertainties. To control the dependence of the neural network function to variations of the input space within these systematic uncertainties, several methods have been proposed. In this work, we propose a new approach of training the neural network by introducing penalties on the variation of the neural network output directly in the loss function. This is achieved at the cost of only a small number of additional hyperparameters. It can also be pursued by treating all systematic variations in the form of statistical weights. The proposed method is demonstrated with a simple example, based on pseudo-experiments, and by a more complex example from high-energy particle physics.

## 16787. SRNet: Structured Relevance Feature Learning Network From Skeleton Data for Human Action Recognition

- 标题：SRNet: Structured Relevance Feature Learning Network From Skeleton Data for Human Action Recognition
- 作者：Weizhi Nie, Wei Wang, Xiangdong Huang
- 年份：2019
- 出版日期：2019-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2019.2940281
- OpenAlex ID：https://openalex.org/W2972327058
- 落地页：https://doi.org/10.1109/access.2019.2940281
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/8600701/08832127.pdf
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Gait Recognition and Analysis, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Skeleton (computer programming), Pattern recognition (psychology), Feature learning, Human skeleton, Feature extraction, Representation (politics), Frame (networking), Feature (linguistics), Convolutional neural network, Relevance (law), Computer vision
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In recent years, human action recognition based on skeleton information has recently drawn increasing attention with published large-scale skeleton datasets. The most crucial factors for this task line in two aspects: the intra-frame representation for joint co-occurrences and the inter-frame representation for skeletons' temporal evolution. The most effective ways focus on spontaneous feature extraction by using deep learning. However, they ignore the structure information of skeleton joints and the correlation between two different skeleton joints for human action recognition. In this paper, we do not simply treat the joints position information as unordered points. Instead, we propose a novel data reorganizing strategy to represent the global and local structure information of human skeleton joints. Meanwhile, we also employ the data mirror to increase the relationship between skeleton joints. Based on this design, we proposed an end-to-end multi-dimensional CNN network (SRNet) to fully consider the spatial and temporal information to learn the feature extraction transform function. Specifically, in this CNN network, we employ different convolution kernels on different dimensions to learn skeleton representation to make the most of human structural information to generate robust features. Finally, we compare with other state-of-the-art on action recognition datasets like NTU RGB+D, PKU-MMD, SYSU, UT-Kinect, and HDM05. The experimental results also demonstrate the superiority of our method.

## 16788. Online Fast Adaptive Low-Rank Similarity Learning for Cross-Modal Retrieval

- 标题：Online Fast Adaptive Low-Rank Similarity Learning for Cross-Modal Retrieval
- 作者：Yiling Wu, Shuhui Wang, Qingming Huang
- 年份：2019
- 出版日期：2019-09-20
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2019.2942494
- OpenAlex ID：https://openalex.org/W2974592692
- 落地页：https://doi.org/10.1109/tmm.2019.2942494
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Similarity learning, Artificial intelligence, Similarity (geometry), Hinge loss, Rank (graph theory), Modal, Data mining, Pattern recognition (psychology), Support vector machine, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The semantic similarity among cross-modal data objects, e.g., similarities between images and texts, are recognized as the bottleneck of cross-modal retrieval. However, existing batch-style correlation learning methods suffer from prohibitive time complexity and extra memory consumption in handling large-scale high dimensional cross-modal data. In this paper, we propose a Cross-Modal Online Low-Rank Similarity function learning (CMOLRS) method, which learns a low-rank bilinear similarity measurement for cross-modal retrieval. We model the cross-modal relations by relative similarities on the training data triplets and formulate the relative relations as convex hinge loss. By adapting the margin in hinge loss with pair-wise distances in feature space and label space, CMOLRS effectively captures the multi-level semantic correlation and adapts to the content divergence among cross-modal data. Imposed with a low-rank constraint, the similarity function is trained by online learning in the manifold of low-rank matrices. The low-rank constraint not only endows the model learning process with faster speed and better scalability, but also improves the model generality. We further propose fast-CMOLRS combining multiple triplets for each query instead of standard process using single triplet at each model update step, which further reduces the times of gradient updates and retractions. Extensive experiments are conducted on four public datasets, and comparisons with state-of-the-art methods show the effectiveness and efficiency of our approach.

## 16789. Worst-case Satisfaction of STL Specifications Using Feedforward Neural Network Controllers

- 标题：Worst-case Satisfaction of STL Specifications Using Feedforward Neural Network Controllers
- 作者：Shakiba Yaghoubi, Georgios Fainekos
- 年份：2019
- 出版日期：2019-10-08
- 类型：article
- 语言：en
- 来源：ACM Transactions on Embedded Computing Systems
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1539-9087
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1145/3358239
- OpenAlex ID：https://openalex.org/W2979818850
- 落地页：https://doi.org/10.1145/3358239
- 开放 PDF 链接：https://dl.acm.org/doi/pdf/10.1145/3358239
- 主主题：Formal Methods in Verification
- 主题：Formal Methods in Verification, Adversarial Robustness in Machine Learning, Receptor Mechanisms and Signaling
- 关键词：Computer science, Robustness (evolution), Artificial neural network, Maximization, Minification, Lagrange multiplier, Nonlinear system, Reinforcement learning, Feedforward neural network, Constraint satisfaction, Set (abstract data type), Feed forward, Mathematical optimization, Algorithm, Artificial intelligence, Control engineering, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this paper, a reinforcement learning approach for designing feedback neural network controllers for nonlinear systems is proposed. Given a Signal Temporal Logic (STL) specification which needs to be satisfied by the system over a set of initial conditions, the neural network parameters are tuned in order to maximize the satisfaction of the STL formula. The framework is based on a max-min formulation of the robustness of the STL formula. The maximization is solved through a Lagrange multipliers method, while the minimization corresponds to a falsification problem. We present our results on a vehicle and a quadrotor model and demonstrate that our approach reduces the training time more than 50 percent compared to the baseline approach.

## 16790. Decompositions of Semidefinite Matrices and the Perspective Reformulation of Nonseparable Quadratic Programs

- 标题：Decompositions of Semidefinite Matrices and the Perspective Reformulation of Nonseparable Quadratic Programs
- 作者：Antonio Frangioni, Claudio Gentile, James T. Hungerford
- 年份：2019
- 出版日期：2019-10-16
- 类型：article
- 语言：en
- 来源：Mathematics of Operations Research
- 来源类型：journal
- 出版方：Institute for Operations Research and the Management Sciences
- ISSN-L：0364-765X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1287/moor.2018.0969
- OpenAlex ID：https://openalex.org/W2980668405
- 落地页：https://doi.org/10.1287/moor.2018.0969
- 主主题：Advanced Optimization Algorithms Research
- 主题：Advanced Optimization Algorithms Research, Sparse and Compressive Sensing Techniques, Machine Learning and Algorithms
- 关键词：Mathematics, Semidefinite programming, Semidefinite embedding, Positive-definite matrix, Quadratically constrained quadratic program, Hessian matrix, Matrix (chemical analysis), Mathematical optimization, Convex optimization, Hermitian matrix, Combinatorics, Heuristic, Applied mathematics, Regular polygon, Discrete mathematics, Quadratic programming, Pure mathematics, Eigenvalues and eigenvectors
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We study the problem of decomposing the Hessian matrix of a mixed integer convex quadratic program (MICQP) into the sum of positive semidefinite 2 × 2 matrices. Solving this problem enables the use of perspective reformulation techniques for obtaining strong lower bounds for MICQPs with semicontinuous variables but a nonseparable objective function. An explicit formula is derived for constructing 2 × 2 decompositions when the underlying matrix is weakly scaled diagonally dominant, and necessary and sufficient conditions are given for the decomposition to be unique. For matrices lying outside this class, two exact semidefinite programming approaches and an efficient heuristic are developed for finding approximate decompositions. We present preliminary results on the bound strength of a 2 × 2 perspective reformulation for the portfolio optimization problem, showing that, for some classes of instances, the use of 2 × 2 matrices can significantly improve the quality of the bound with respect to the best previously known approach, although at a possibly high computational cost.

## 16791. Malicious PDF Detection Model against Adversarial Attack Built from Benign PDF Containing JavaScript

- 标题：Malicious PDF Detection Model against Adversarial Attack Built from Benign PDF Containing JavaScript
- 作者：Ah Reum Kang, Young-Seob Jeong, Se‐Kwon Kim, Jiyoung Woo
- 年份：2019
- 出版日期：2019-11-08
- 类型：article
- 语言：en
- 来源：Applied Sciences
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2076-3417
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/app9224764
- OpenAlex ID：https://openalex.org/W2984061032
- 落地页：https://doi.org/10.3390/app9224764
- 开放 PDF 链接：https://www.mdpi.com/2076-3417/9/22/4764/pdf
- 主主题：Advanced Malware Detection Techniques
- 主题：Advanced Malware Detection Techniques, Adversarial Robustness in Machine Learning, Security and Verification in Computing
- 关键词：Malware, Computer science, JavaScript, Adversarial system, Metadata, Exploit, Artificial intelligence, Data mining, Information retrieval, Machine learning, Computer security, World Wide Web
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Intelligent attacks using document-based malware that exploit vulnerabilities in document viewing software programs or document file structure are increasing rapidly. There are many cases of using PDF (portable document format) in proportion to its usage. We provide in-depth analysis on PDF structure and JavaScript content embedded in PDFs. Then, we develop the diverse feature set encompassing the structure and metadata such as file size, version, encoding method and keywords, and the content features such as object names, keywords, and readable strings in JavaScript. When features are diverse, it is hard to develop adversarial examples because small changes are robust for machine-learning algorithms. We develop a detection model using black-box type models with the structure and content features to minimize the risk of adversarial attacks. To validate the proposed model, we design the adversarial attack. We collect benign documents containing multiple JavaScript codes for the base of adversarial samples. We build the adversarial samples by injecting the malware codes into base samples. The proposed model is evaluated against a large collection of malicious and benign PDFs. We found that random forest, an ensemble algorithm of a decision tree, exhibits a good performance on malware detection and is robust for adversarial samples.

## 16792. Embedded adaptive cross-modulation neural network for few-shot learning

- 标题：Embedded adaptive cross-modulation neural network for few-shot learning
- 作者：Peng Wang, Jun Cheng, Fusheng Hao, Lei Wang, Wei Feng
- 年份：2019
- 出版日期：2019-11-16
- 类型：article
- 语言：en
- 来源：Neural Computing and Applications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0941-0643
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00521-019-04605-y
- OpenAlex ID：https://openalex.org/W2984260139
- 落地页：https://doi.org/10.1007/s00521-019-04605-y
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Embedding, Robustness (evolution), Machine learning, Test set, Metric (unit), Generalization, Artificial neural network, Feature vector, Abstraction, Set (abstract data type), Pattern recognition (psychology), Feature learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16793. An Approach to Hyperparameter Optimization for the Objective Function in Machine Learning

- 标题：An Approach to Hyperparameter Optimization for the Objective Function in Machine Learning
- 作者：Yonghoon Kim, Mokdong Chung
- 年份：2019
- 出版日期：2019-11-01
- 类型：article
- 语言：en
- 来源：Electronics
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2079-9292
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/electronics8111267
- OpenAlex ID：https://openalex.org/W2988011443
- 落地页：https://doi.org/10.3390/electronics8111267
- 开放 PDF 链接：https://www.mdpi.com/2079-9292/8/11/1267/pdf
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Gaussian Processes and Bayesian Inference, Advanced Multi-Objective Optimization Algorithms
- 关键词：Hyperparameter, Machine learning, Bayesian optimization, Artificial intelligence, Computer science, Gaussian process, Regularization (linguistics), Wake-sleep algorithm, Online machine learning, Bayesian probability, Semi-supervised learning, Gaussian, Unsupervised learning, Generalization error
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In machine learning, performance is of great value. However, each learning process requires much time and effort in setting each parameter. The critical problem in machine learning is determining the hyperparameters, such as the learning rate, mini-batch size, and regularization coefficient. In particular, we focus on the learning rate, which is directly related to learning efficiency and performance. Bayesian optimization using a Gaussian Process is common for this purpose. In this paper, based on Bayesian optimization, we attempt to optimize the hyperparameters automatically by utilizing a Gamma distribution, instead of a Gaussian distribution, to improve the training performance of predicting image discrimination. As a result, our proposed method proves to be more reasonable and efficient in the estimation of learning rate when training the data, and can be useful in machine learning.

## 16794. Generating Semantically Similar and Human-Readable Summaries With Generative Adversarial Networks

- 标题：Generating Semantically Similar and Human-Readable Summaries With Generative Adversarial Networks
- 作者：Haojie Zhuang, Weibin Zhang
- 年份：2019
- 出版日期：2019-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2019.2955087
- OpenAlex ID：https://openalex.org/W2992062333
- 落地页：https://doi.org/10.1109/access.2019.2955087
- 主主题：Topic Modeling
- 主题：Topic Modeling, Natural Language Processing Techniques, Multimodal Machine Learning Applications
- 关键词：Automatic summarization, Computer science, Generator (circuit theory), Discriminator, Adversarial system, Artificial intelligence, Generative grammar, Process (computing), Representation (politics), Natural language processing, Artificial neural network, Natural language generation, Task (project management), Core (optical fiber), Natural language, Semantics (computer science), Machine learning, Programming language, Power (physics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The application of neural networks in natural language processing, including abstractive text summarization, is increasingly attractive in recent years. However, teaching a neural network to generate a human-readable summary that reflects the core idea of the original source text (i.e., semantically similar) remains a challenging problem. In this paper, we explore using generative adversarial networks to solve this problem. The proposed model contains three components: a generator that encodes the long input text into a shorter representation; a discriminator to teach the generator to create human-readable summaries and another discriminator to restrict the output of the generator to reflect the core idea of the input text. The main training process can be carried out in an adversarial learning process. To solve the non-differentiable problem caused by the words sampling process, we use the policy gradient algorithm to optimize the generator. We evaluate the proposed model on the CNN/Daily Mail summarization task. The experimental results show that the model outperforms previous state-of-the-art models.

## 16795. Histogram of Fuzzy Local Spatio-Temporal Descriptors for Video Action Recognition

- 标题：Histogram of Fuzzy Local Spatio-Temporal Descriptors for Video Action Recognition
- 作者：Zheming Zuo, Longzhi Yang, Yonghuai Liu, Fei Chao, Ran Song, Yanpeng Qu
- 年份：2019
- 出版日期：2019-12-03
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Industrial Informatics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1551-3203
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tii.2019.2957268
- OpenAlex ID：https://openalex.org/W2992972104
- 落地页：https://doi.org/10.1109/tii.2019.2957268
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Video Surveillance and Tracking Methods, Multimodal Machine Learning Applications
- 关键词：Histogram, Artificial intelligence, Computer science, Histogram matching, Pattern recognition (psychology), Optical flow, Pixel, Feature (linguistics), Histogram of oriented gradients, Fuzzy logic, Feature extraction, Computer vision, Fuzzy set, Image (mathematics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Feature extraction plays a vital role in visual action recognition. Many existing gradient-based feature extractors, including histogram of oriented gradients, histogram of optical flow, motion boundary histograms, and histogram of motion gradients, build histograms for representing different actions over the spatio-temporal domain in a video. However, these methods require to set the number of bins for information aggregation in advance. Varying numbers of bins usually lead to inherent uncertainty within the process of pixel voting with regard to the bins in the histogram. This article proposes a novel method to handle such uncertainty by fuzzifying these feature extractors. The proposed approach has two advantages: it better represents the ambiguous boundaries between the bins and, thus, the fuzziness of the spatio-temporal visual information entailed in videos; and the contribution of each pixel is flexibly controlled by a fuzziness parameter for various scenarios. The proposed family of fuzzy descriptors and a combination of them are evaluated on two publicly available datasets, demonstrating that the proposed approach outperforms the original counterparts and other state-of-the-art methods.

## 16796. Rich Features Embedding for Cross-Modal Retrieval: A Simple Baseline

- 标题：Rich Features Embedding for Cross-Modal Retrieval: A Simple Baseline
- 作者：Xin Fu, Yao Zhao, Yunchao Wei, Yufeng Zhao, Shikui Wei
- 年份：2019
- 出版日期：2019-12-12
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2019.2957948
- OpenAlex ID：https://openalex.org/W2996478685
- 落地页：https://doi.org/10.1109/tmm.2019.2957948
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Embedding, Modal, Simple (philosophy), Baseline (sea), Construct (python library), Information retrieval, Artificial intelligence, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
During the past few years, significant progress has been made on cross-modal retrieval, benefiting from the development of deep neural networks. Meanwhile, the overall frameworks are becoming more and more complex, making the training as well as the analysis more difficult. In this paper, we provide a Rich Features Embedding (RFE) approach to tackle the cross-modal retrieval tasks in a simple yet effective way. RFE proposes to construct rich representations for both images and texts, which is further leveraged to learn the rich features embedding in the common space according to a simple hard triplet loss. Without any bells and whistles in constructing complex components, the proposed RFE is concise and easy to implement. More importantly, our RFE obtains the state-of-the-art results on several popular benchmarks such as MS COCO and Flickr 30 K. In particular, the image-to-text and text-to-image retrieval achieve 76.1% and 61.1% (R@1) on MS COCO, which outperform others more than 3.4% and 2.3%, respectively. We hope our RFE will serve as a solid baseline and help ease future research in cross-modal retrieval.

## 16797. Zero-shot learning by mutual information estimation and maximization

- 标题：Zero-shot learning by mutual information estimation and maximization
- 作者：Chenwei Tang, Xue Yang, Jiancheng Lv, Zhenan He
- 年份：2020
- 出版日期：2020-01-14
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2020.105490
- OpenAlex ID：https://openalex.org/W2999359505
- 落地页：https://doi.org/10.1016/j.knosys.2020.105490
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Machine Learning and ELM, Multimodal Machine Learning Applications
- 关键词：Mutual information, Artificial intelligence, Computer science, Embedding, Pattern recognition (psychology), Maximization, Estimator, Matching (statistics), Noise (video), Image (mathematics), Machine learning, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16798. A Survey on Machine Learning Adversarial Attacks

- 标题：A Survey on Machine Learning Adversarial Attacks
- 作者：Flávio Luís de Mello
- 年份：2020
- 出版日期：2020-01-20
- 类型：article
- 语言：en
- 来源：Journal of Information Security and Cryptography (Enigma)
- 来源类型：journal
- ISSN-L：2595-5217
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.17648/jisc.v7i1.76
- OpenAlex ID：https://openalex.org/W3004478028
- 落地页：https://doi.org/10.17648/jisc.v7i1.76
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Advanced Malware Detection Techniques
- 关键词：Adversarial machine learning, Adversarial system, Compromise, Computer science, Leverage (statistics), Machine learning, Robustness (evolution), Computer security, Artificial intelligence, Threat model
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
It is becoming notorious several types of adversaries based on their threat model leverage vulnerabilities to compromise a machine learning system. Therefore, it is important to provide robustness to machine learning algorithms and systems against these adversaries. However, there are only a few strong countermeasures, which can be used in all types of attack scenarios to design a robust artificial intelligence system. This paper is structured and comprehensive overview of the research on attacks to machine learning systems and it tries to call the attention from developers and software houses to the security issues concerning machine learning.

## 16799. Deep Multiphase Level Set for Scene Parsing

- 标题：Deep Multiphase Level Set for Scene Parsing
- 作者：Pingping Zhang, Wei Liu, Yinjie Lei, Hongyu Wang, Huchuan Lu
- 年份：2020
- 出版日期：2020-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tip.2019.2957915
- OpenAlex ID：https://openalex.org/W3007072719
- 落地页：https://doi.org/10.1109/tip.2019.2957915
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Advanced Neural Network Applications, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Parsing, Discriminative model, Convolutional neural network, Segmentation, Pixel, Pattern recognition (psychology), Set (abstract data type), Image segmentation, Deep learning, Boundary (topology), Machine learning, Computer vision, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Recently, Fully Convolutional Network (FCN) seems to be the go-to architecture for image segmentation, including semantic scene parsing. However, it is difficult for a generic FCN to predict semantic labels around the object boundaries, thus FCN-based methods usually produce parsing results with inaccurate boundaries. Meanwhile, many works have demonstrate that level set based active contours are superior to the boundary estimation in sub-pixel accuracy. However, they are quite sensitive to initial settings. To address these limitations, in this paper we propose a novel Deep Multiphase Level Set (DMLS) method for semantic scene parsing, which efficiently incorporates multiphase level sets into deep neural networks. The proposed method consists of three modules, i.e., recurrent FCNs, adaptive multiphase level set, and deeply supervised learning. More specifically, recurrent FCNs learn multi-level representations of input images with different contexts. Adaptive multiphase level set drives the discriminative contour for each semantic class, which makes use of the advantages of both global and local information. In each time-step of the recurrent FCNs, deeply supervised learning is incorporated for model training. Extensive experiments on three public benchmarks have shown that our proposed method achieves new state-of-the-art performances. The source codes will be released at https://github.com/Pchank/DMLS-for-SSP.

## 16800. Learning skeleton information for human action analysis using Kinect

- 标题：Learning skeleton information for human action analysis using Kinect
- 作者：Gang Li, Chunyu Li
- 年份：2020
- 出版日期：2020-02-24
- 类型：article
- 语言：en
- 来源：Signal Processing Image Communication
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0923-5965
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.image.2020.115814
- OpenAlex ID：https://openalex.org/W3007986639
- 落地页：https://doi.org/10.1016/j.image.2020.115814
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Video Analysis and Summarization, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Action recognition, Robustness (evolution), Computer vision, Human skeleton, Action (physics), Human body, Matching (statistics), Pattern recognition (psychology), Human–computer interaction, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16801. Attribute-Guided Attention for Referring Expression Generation and Comprehension

- 标题：Attribute-Guided Attention for Referring Expression Generation and Comprehension
- 作者：Jingyu Liu, Wei Wang, Liang Wang, Ming–Hsuan Yang
- 年份：2020
- 出版日期：2020-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2020.2979010
- OpenAlex ID：https://openalex.org/W3010803012
- 落地页：https://doi.org/10.1109/tip.2020.2979010
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Advanced Image and Video Retrieval Techniques
- 关键词：Computer science, Comprehension, Expression (computer science), Artificial intelligence, Natural language processing, Visualization, Object (grammar), Representation (politics), Field (mathematics), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Referring expression is a special kind of verbal expression. The goal of referring expression is to refer to a particular object in some scenarios. Referring expression generation and comprehension are two inverse tasks within the field. Considering the critical role that visual attributes play in distinguishing the referred object from other objects, we propose an attribute-guided attention model to address the two tasks. In our proposed framework, attributes collected from referring expressions are used as explicit supervision signals on the generation and comprehension modules. The online predicted attributes of the visual object can benefit both tasks in two aspects: First, attributes can be directly embedded into the generation and comprehension modules, distinguishing the referred object as additional visual representations. Second, since attributes have their correspondence in both visual and textual space, an attribute-guided attention module is proposed as a bridging part to link the counterparts in visual representation and textual expression. Attention weights learned on both visual feature and word embeddings validate our motivation. We experiment on three standard datasets of RefCOCO, RefCOCO+ and RefCOCOg commonly used in this field. Both quantitative and qualitative results demonstrate the effectiveness of our proposed framework. The experimental results show significant improvements over baseline methods, and are favorably comparable to the state-of-the-art results. Further ablation study and analysis clearly demonstrate the contribution of each module, which could provide useful inspirations to the community.

## 16802. Practical Challenges and Recommendations of Filter Methods for Feature Selection

- 标题：Practical Challenges and Recommendations of Filter Methods for Feature Selection
- 作者：Mohammed Rajab, Dennis Wang
- 年份：2020
- 出版日期：2020-03-01
- 类型：article
- 语言：en
- 来源：Journal of Information & Knowledge Management
- 来源类型：journal
- 出版方：World Scientific
- ISSN-L：0219-6492
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1142/s0219649220400195
- OpenAlex ID：https://openalex.org/W3014090520
- 落地页：https://doi.org/10.1142/s0219649220400195
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Face and Expression Recognition, Evolutionary Algorithms and Applications
- 关键词：Computer science, Feature selection, Machine learning, Filter (signal processing), Artificial intelligence, Classifier (UML), Process (computing), Curse of dimensionality, Big data, Data mining, Feature (linguistics), Selection (genetic algorithm), Dimensionality reduction
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Feature selection, the process of identifying relevant features to be incorporated into a proposed model, is one of the significant steps of the learning process. It removes noise from the data to increase the learning performance while reducing the computational complexity. The literature review indicated that most previous studies had focused on improving the overall classifier performance or reducing costs associated with training time during building of the classifiers. However, in this era of big data, there is an urgent need to deal with more complex issues that makes feature selection, especially using filter-based methods, more challenging; this in terms of dimensionality, data structures, data format, domain experts’ availability, data sparsity, and result discrepancies, among others. Filter methods identify the informative features of a given dataset to establish various predictive models using mathematical models. This paper takes a new route in an attempt to pinpoint recent practical challenges associated with filter methods and discusses potential areas of development to yield better performance. Several practical recommendations, based on recent studies, are made to overcome the identified challenges and make the feature selection process simpler and more efficient.

## 16803. SA-NLI: A Supervised Attention based framework for Natural Language Inference

- 标题：SA-NLI: A Supervised Attention based framework for Natural Language Inference
- 作者：Peiguang Li, Hongfeng Yu, Wenkai Zhang, Guangluan Xu, Xian Sun
- 年份：2020
- 出版日期：2020-04-09
- 类型：article
- 语言：en
- 来源：Neurocomputing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0925-2312
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neucom.2020.03.092
- OpenAlex ID：https://openalex.org/W3015889210
- 落地页：https://doi.org/10.1016/j.neucom.2020.03.092
- 主主题：Topic Modeling
- 主题：Topic Modeling, Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning
- 关键词：Interpretability, Computer science, Generalization, Artificial intelligence, Inference, Natural language processing, Focus (optics), Representation (politics), Machine learning, Parametric statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16804. Exploiting Vulnerabilities of Deep Neural Networks for Privacy Protection

- 标题：Exploiting Vulnerabilities of Deep Neural Networks for Privacy Protection
- 作者：Ricardo Sanchez-Matilla, Chau Yi Li, Ali Shahin Shamsabadi, Riccardo Mazzon, Andrea Cavallaro
- 年份：2020
- 出版日期：2020-04-16
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tmm.2020.2987694
- OpenAlex ID：https://openalex.org/W3016308890
- 落地页：https://doi.org/10.1109/tmm.2020.2987694
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Generative Adversarial Networks and Image Synthesis, Digital Media Forensic Detection
- 关键词：Overfitting, Classifier (UML), Adversarial system, Adversarial machine learning, Artificial neural network, Process (computing), Pattern recognition (psychology), Deep neural networks
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Adversarial perturbations can be added to images to protect their content from unwanted inferences. These perturbations may, however, be ineffective against classifiers that were not seen during the generation of the perturbation, or against defenses based on re-quantization, median filtering or JPEG compression. To address these limitations, we present an adversarial attack that is specifically designed to protect visual content against unseen classifiers and known defenses. We craft perturbations using an iterative process that is based on the Fast Gradient Signed Method and that randomly selects a classifier and a defense, at each iteration. This randomization prevents an undesirable overfitting to a specific classifier or defense. We validate the proposed attack in both targeted and untargeted settings on the private classes of the Places365-Standard dataset. Using ResNet18, ResNet50, AlexNet and DenseNet161 as classifiers, the performance of the proposed attack exceeds that of eleven state-of-the-art attacks.

## 16805. MII: A Novel Text Classification Model Combining Deep Active Learning with BERT

- 标题：MII: A Novel Text Classification Model Combining Deep Active Learning with BERT
- 作者：Anman Zhang, Bohan Li, Wen-Huan Wang, Shuo Wan, Weitong Chen
- 年份：2020
- 出版日期：2020-01-01
- 类型：article
- 语言：en
- 来源：Computers, materials & continua/Computers, materials & continua (Print)
- 来源类型：journal
- ISSN-L：1546-2218
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.32604/cmc.2020.09962
- OpenAlex ID：https://openalex.org/W3022558583
- 落地页：https://doi.org/10.32604/cmc.2020.09962
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Machine Learning and Data Classification, Text and Document Classification Technologies
- 关键词：Computer science, Artificial intelligence, Machine learning, Deep learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Active learning has been widely utilized to reduce the labeling cost of supervised learning. By selecting specific instances to train the model, the performance of the model was improved within limited steps. However, rar... | Find, read and cite all the research you need on Tech Science Press

## 16806. CNN-on-AWS: Efficient Allocation of Multikernel Applications on Multi-FPGA Platforms

- 标题：CNN-on-AWS: Efficient Allocation of Multikernel Applications on Multi-FPGA Platforms
- 作者：Junnan Shan, Mihai T. Lazarescu, Jordi Cortadella, Luciano Lavagno, Mario R. Casu
- 年份：2020
- 出版日期：2020-05-12
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Computer-Aided Design of Integrated Circuits and Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0278-0070
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tcad.2020.2994256
- OpenAlex ID：https://openalex.org/W3025152414
- 落地页：https://doi.org/10.1109/tcad.2020.2994256
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications
- 关键词：Field-programmable gate array, Computer science, Parallel computing, Solver, Kernel (algebra), Pipeline (software), Convolutional neural network, Heuristic, Computation, Embedded system, Algorithm, Artificial intelligence, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Multi-FPGA platforms, like Amazon AWS F1, can run in the cloud multikernel pipelined applications, like convolutional neural networks (CNNs), with excellent performance and lower energy consumption than CPUs or GPUs. We propose a method to efficiently map these applications on multi-FPGA platforms to maximize the application throughput. Our methodology finds, for the given resources, the optimal number of parallel instances of each kernel in the pipeline and their allocation to one or more among the available FPGAs. We obtain this by formulating and solving a mixed-integer, nonlinear optimization problem, in which we model the performance of each component and the duration of the phases in which the accelerated computation can be split into, namely: 1) data transfer from a host CPU to the DDR memory of each FPGA; 2) data transfer from FPGA DDR to FPGA on-chip memory; 3) kernel computation on the FPGA; 4) data transfer from FPGA on-chip memory to FPGA DDR; and 5) data transfer from FPGA DDR to host. Finding the optimal solution using a mixed-integer nonlinear programming (MINLP) solver is often highly inefficient. Hence, we provide a fast heuristic method that according to our experiments can be much more efficient than the MINLP solver and finds comparable results. For larger problems (more CNN layers), our heuristic method can quickly find (several thousand times faster) much better solutions than the MINLP solver, even if we run the latter for a very long time.

## 16807. LPG-model: A novel model for throughput prediction in stream processing, using a light gradient boosting machine, incremental principal component analysis, and deep gated recurrent unit network

- 标题：LPG-model: A novel model for throughput prediction in stream processing, using a light gradient boosting machine, incremental principal component analysis, and deep gated recurrent unit network
- 作者：Zheng Chu, Jiong Yu, Askar Hamdulla
- 年份：2020
- 出版日期：2020-05-23
- 类型：article
- 语言：en
- 来源：Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0255
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ins.2020.05.042
- OpenAlex ID：https://openalex.org/W3028249963
- 落地页：https://doi.org/10.1016/j.ins.2020.05.042
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Machine Learning and Data Classification, Anomaly Detection Techniques and Applications
- 关键词：Computer science, Normalization (sociology), Artificial intelligence, Boosting (machine learning), Data stream mining, Principal component analysis, Data mining, Stream processing, Scheduling (production processes), Gradient boosting, Preprocessor, Data pre-processing, Machine learning, Distributed computing, Random forest, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16808. Explaining VQA predictions using visual grounding and a knowledge base

- 标题：Explaining VQA predictions using visual grounding and a knowledge base
- 作者：Felipe Riquelme, Alfredo De Goyeneche, Yundong Zhang, Juan Carlos Niebles, Álvaro Soto
- 年份：2020
- 出版日期：2020-06-28
- 类型：article
- 语言：en
- 来源：Image and Vision Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0262-8856
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.imavis.2020.103968
- OpenAlex ID：https://openalex.org/W3037011828
- 落地页：https://doi.org/10.1016/j.imavis.2020.103968
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning, Advanced Image and Video Retrieval Techniques
- 关键词：Interpretability, Computer science, Complement (music), Visualization, Artificial intelligence, Task (project management), Object (grammar), Question answering, Point (geometry), Machine learning, Knowledge base, Image (mathematics), Natural language processing, Information retrieval, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16809. Image Captioning with a Joint Attention Mechanism by Visual Concept Samples

- 标题：Image Captioning with a Joint Attention Mechanism by Visual Concept Samples
- 作者：Jin Yuan, Lei Zhang, Songrui Guo, Yi Xiao, Zhiyong Li
- 年份：2020
- 出版日期：2020-07-05
- 类型：article
- 语言：en
- 来源：ACM Transactions on Multimedia Computing Communications and Applications
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1551-6857
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/3394955
- OpenAlex ID：https://openalex.org/W3038593179
- 落地页：https://doi.org/10.1145/3394955
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Closed captioning, Computer science, Joint (building), Artificial intelligence, Image (mathematics), Mechanism (biology), Word (group theory), Visualization, Bridge (graph theory), Natural language processing, Domain (mathematical analysis), Pattern recognition (psychology), Machine learning, Linguistics, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The attention mechanism has been established as an effective method for generating caption words in image captioning; it explores one noticed subregion in an image to predict a related caption word. However, even though the attention mechanism could offer accurate subregions to train a model, the learned captioner may predict wrong, especially for visual concept words, which are the most important parts to understand an image. To tackle the preceding problem, in this article we propose Visual Concept Enhanced Captioner, which employs a joint attention mechanism with visual concept samples to strengthen prediction abilities for visual concepts in image captioning. Different from traditional attention approaches that adopt one LSTM to explore one noticed subregion each time, Visual Concept Enhanced Captioner introduces multiple virtual LSTMs in parallel to simultaneously receive multiple subregions from visual concept samples. Then, the model could update parameters by jointly exploring these subregions according to a composite loss function. Technically, this joint learning is helpful in finding the common characters of a visual concept, and thus it enhances the prediction accuracy for visual concepts. Moreover, by integrating diverse visual concept samples from different domains, our model can be extended to bridge visual bias in cross-domain learning for image captioning, which saves the cost for labeling captions. Extensive experiments have been conducted on two image datasets (MSCOCO and Flickr30K), and superior results are reported when comparing to state-of-the-art approaches. It is impressive that our approach could significantly increase BLUE-1 and F1 scores, which demonstrates an accuracy improvement for visual concepts in image captioning.

## 16810. Multi-models of Educational Data Mining for Predicting Student Performance in Mathematics: A Case Study on High Schools in Cambodia

- 标题：Multi-models of Educational Data Mining for Predicting Student Performance in Mathematics: A Case Study on High Schools in Cambodia
- 作者：Phauk Sokkhey, Sin Navy, Ly Tong, Okazaki Takeo
- 年份：2020
- 出版日期：2020-06-30
- 类型：article
- 语言：en
- 来源：IEIE Transactions on Smart Processing and Computing
- 来源类型：journal
- ISSN-L：2287-5255
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.5573/ieiespc.2020.9.3.217
- OpenAlex ID：https://openalex.org/W3038720994
- 落地页：https://doi.org/10.5573/ieiespc.2020.9.3.217
- 主主题：Online Learning and Analytics
- 主题：Online Learning and Analytics, Machine Learning and Data Classification, Software System Performance and Reliability
- 关键词：Computer science, Random forest, Information gain ratio, Machine learning, Educational data mining, Artificial intelligence, Feature selection, Decision tree, Feature (linguistics), Data mining, Mean squared error, Statistics, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Education is crucial for the development of any country. Analysis of education datasets requires effective algorithms to extract hidden information and gain the fruitful results to improve academic performance. Multiple models were used to maximize the contribution to the education environment. In this study, we used the spot-checking algorithm to compare these methods and find the most effective method. We propose three main classes of education research tools: a statistical analysis method, machine learning algorithms, and a deep learning framework. The data were obtained from many high schools in Cambodia. We introduced feature selection techniques to figure out the informative features that affect the future performance of students in mathematics. The proposed ensemble methods of tree-based classifiers provide satisfiying results, and in that, random forest algorithm generates the highest accuracy and the lowest predictive mean squared error, thus showing potential in this prediction and classification problem. The results from this work can be used as recipe and recommendation for mining various material settings in improving high school student performance in Cambodia.

## 16811. Adversarial Tri-Fusion Hashing Network for Imbalanced Cross-Modal Retrieval

- 标题：Adversarial Tri-Fusion Hashing Network for Imbalanced Cross-Modal Retrieval
- 作者：Xin Liu, Yiu‐ming Cheung, Zhikai Hu, Yi He, Bineng Zhong
- 年份：2020
- 出版日期：2020-07-13
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Emerging Topics in Computational Intelligence
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2471-285X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tetci.2020.3007143
- OpenAlex ID：https://openalex.org/W3042596116
- 落地页：https://doi.org/10.1109/tetci.2020.3007143
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications, Video Analysis and Summarization
- 关键词：Computer science, Semantic gap, Hamming space, Hash function, Modal, Artificial intelligence, Benchmark (surveying), Machine learning, Feature learning, Data mining, Information retrieval, Hamming code, Algorithm, Image retrieval
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Cross-modal retrieval has received increasing attentions for efficient retrieval across different modalities, and hashing technique has made significant progress recently due to its low storage cost and high query speed. However, most existing cross-modal hashing works still face the challenges of narrowing down the semantic gap between different modalities and training with imbalanced multi-modal data. This article presents an efficient Adversarial Tri-Fusion Hashing Network (ATFH-N) for cross-modal retrieval, which lies among the early attempts to incorporate adversarial learning for working with imbalanced multi-modal data. Specifically, a triple fusion network associated with zero padding operation is proposed to adapt either balanced or imbalanced multi-modal training data. At the same time, an adversarial training mechanism is leveraged to maximally bridge the semantic gap of the common representations between balanced and imbalanced data. Further, a label prediction network is utilized to guide the feature learning process and promote hash code learning, while additionally embedding the manifold structure to preserve both inter-modal and intra-modal similarities. Through the joint exploitation of the above, the underlying semantic structure of multimedia data can be well preserved in Hamming space, which can benefit various cross-modal retrieval tasks. Extensive experiments on three benchmark datasets show that the proposed ATFH-N method yields the comparable performance in balanced scenario and brings substantial improvements over the state-of-the-art methods in imbalanced scenarios.

## 16812. Convergence Analysis of Hybrid Control Systems in the Form of Backward Chained Behavior Trees

- 标题：Convergence Analysis of Hybrid Control Systems in the Form of Backward Chained Behavior Trees
- 作者：Petter Ögren
- 年份：2020
- 出版日期：2020-07-21
- 类型：article
- 语言：en
- 来源：IEEE Robotics and Automation Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2377-3766
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/lra.2020.3010747
- OpenAlex ID：https://openalex.org/W3044207482
- 落地页：https://doi.org/10.1109/lra.2020.3010747
- 主主题：Formal Methods in Verification
- 主题：Formal Methods in Verification, Reinforcement Learning in Robotics, Machine Learning and Algorithms
- 关键词：Control theory (sociology), Convergence (economics), Computer science, Controller (irrigation), Tree (set theory), Set (abstract data type), Control (management), Task (project management), State (computer science), Finite-state machine, Control engineering, Mathematics, Engineering, Artificial intelligence, Algorithm, Economics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A robot control system is often composed of a set of low level continuous controllers and a switching policy that decides which of those continuous controllers to apply at each time instant. The switching policy can be either a Finite State Machine (FSM), a Behavior Tree (BT) or some other structure. In previous work we have shown how to create BTs using a backward chained approach that results in a reactive goal directed policy. This policy can be thought of as providing disturbance rejection at the task level in the sense that if a disturbance changes the state in such a way that the currently running continuous controller cannot handle it, the policy will switch to the appropriate continuous controller. In this letter we show how to provide convergence guarantees for such policies.

## 16813. A Novel Penalty-Based Wrapper Objective Function for Feature Selection in Big Data Using Cooperative Co-Evolution

- 标题：A Novel Penalty-Based Wrapper Objective Function for Feature Selection in Big Data Using Cooperative Co-Evolution
- 作者：Ayesha Rashid, Mohiuddin Ahmed, Leslie F. Sikos, Paul Haskell‐Dowland
- 年份：2020
- 出版日期：2020-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2020.3016679
- OpenAlex ID：https://openalex.org/W3049721772
- 落地页：https://doi.org/10.1109/access.2020.3016679
- 主主题：Evolutionary Algorithms and Applications
- 主题：Evolutionary Algorithms and Applications, Metaheuristic Optimization Algorithms Research, Machine Learning and Data Classification
- 关键词：Computer science, Feature selection, Naive Bayes classifier, Curse of dimensionality, Big data, Artificial intelligence, Preprocessor, Feature (linguistics), Data pre-processing, Selection (genetic algorithm), Evolutionary algorithm, Machine learning, Data mining, Statistical classification, Evolutionary computation, Function (biology), Pattern recognition (psychology), Support vector machine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The rapid progress of modern technologies generates a massive amount of high-throughput data, called Big Data, which provides opportunities to find new insights using machine learning (ML) algorithms. Big Data consist of many features (also called attributes); however, not all these are necessary or relevant, and they may degrade the performance of ML algorithms. Feature selection (FS) is an essential preprocessing step to reduce the dimensionality of a dataset. Evolutionary algorithms (EAs) are widely used search algorithms for FS. Using classification accuracy as the objective function for FS, EAs, such as the cooperative co-evolutionary algorithm (CCEA), achieve higher accuracy, even with a higher number of features. Feature selection has two purposes: reducing the number of features to decrease computations and improving classification accuracy, which are contradictory but can be achieved using a single objective function. For this very purpose, this paper proposes a penalty-based wrapper objective function. This function can be used to evaluate the FS process using CCEA, hence called Cooperative Co-Evolutionary Algorithm-Based Feature Selection (CCEAFS). An experiment was performed using six widely used classifiers on six different datasets from the UCI ML repository with FS and without FS. The experimental results indicate that the proposed objective function is efficient at reducing the number of features in the final feature subset without significantly reducing classification accuracy. Based on different performance measures, in most cases, naïve Bayes outperforms other classifiers when using CCEAFS.

## 16814. Indoor Scene Change Captioning Based on Multimodality Data

- 标题：Indoor Scene Change Captioning Based on Multimodality Data
- 作者：Yue Qiu, Yutaka Satoh, Ryota Suzuki, Kenji Iwata, Hirokatsu Kataoka
- 年份：2020
- 出版日期：2020-08-23
- 类型：article
- 语言：en
- 来源：Sensors
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：1424-8220
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/s20174761
- OpenAlex ID：https://openalex.org/W3080111863
- 落地页：https://doi.org/10.3390/s20174761
- 开放 PDF 链接：https://www.mdpi.com/1424-8220/20/17/4761/pdf?version=1598176329
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Advanced Image and Video Retrieval Techniques
- 关键词：Computer science, Point cloud, Closed captioning, Change detection, Artificial intelligence, RGB color model, Computer vision, Correctness, Scene statistics, Point (geometry), Image (mathematics), Perception
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This study proposes a framework for describing a scene change using natural language text based on indoor scene observations conducted before and after a scene change. The recognition of scene changes plays an essential role in a variety of real-world applications, such as scene anomaly detection. Most scene understanding research has focused on static scenes. Most existing scene change captioning methods detect scene changes from single-view RGB images, neglecting the underlying three-dimensional structures. Previous three-dimensional scene change captioning methods use simulated scenes consisting of geometry primitives, making it unsuitable for real-world applications. To solve these problems, we automatically generated large-scale indoor scene change caption datasets. We propose an end-to-end framework for describing scene changes from various input modalities, namely, RGB images, depth images, and point cloud data, which are available in most robot applications. We conducted experiments with various input modalities and models and evaluated model performance using datasets with various levels of complexity. Experimental results show that the models that combine RGB images and point cloud data as input achieve high performance in sentence generation and caption correctness and are robust for change type understanding for datasets with high complexity. The developed datasets and models contribute to the study of indoor scene change understanding.

## 16815. The Defense of Adversarial Example with Conditional Generative Adversarial Networks

- 标题：The Defense of Adversarial Example with Conditional Generative Adversarial Networks
- 作者：Fangchao Yu, Li Wang, Xianjin Fang, Youwen Zhang
- 年份：2020
- 出版日期：2020-08-25
- 类型：article
- 语言：en
- 来源：Security and Communication Networks
- 来源类型：journal
- 出版方：Hindawi Publishing Corporation
- ISSN-L：1939-0114
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1155/2020/3932584
- OpenAlex ID：https://openalex.org/W3080490018
- 落地页：https://doi.org/10.1155/2020/3932584
- 开放 PDF 链接：https://downloads.hindawi.com/journals/scn/2020/3932584.pdf
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Advanced Neural Network Applications
- 关键词：Adversarial system, MNIST database, Discriminator, Computer science, Generator (circuit theory), Artificial intelligence, Adversary, Generative grammar, Process (computing), Image (mathematics), Machine learning, Artificial neural network, Deep learning, Computer security, Power (physics)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep neural network approaches have made remarkable progress in many machine learning tasks. However, the latest research indicates that they are vulnerable to adversarial perturbations. An adversary can easily mislead the network models by adding well-designed perturbations to the input. The cause of the adversarial examples is unclear. Therefore, it is challenging to build a defense mechanism. In this paper, we propose an image-to-image translation model to defend against adversarial examples. The proposed model is based on a conditional generative adversarial network, which consists of a generator and a discriminator. The generator is used to eliminate adversarial perturbations in the input. The discriminator is used to distinguish generated data from original clean data to improve the training process. In other words, our approach can map the adversarial images to the clean images, which are then fed to the target deep learning model. The defense mechanism is independent of the target model, and the structure of the framework is universal. A series of experiments conducted on MNIST and CIFAR10 show that the proposed method can defend against multiple types of attacks while maintaining good performance.

## 16816. Interclass-Relativity-Adaptive Metric Learning for Cross-Modal Matching and Beyond

- 标题：Interclass-Relativity-Adaptive Metric Learning for Cross-Modal Matching and Beyond
- 作者：Feiyu Chen, Jie Shao, Yonghui Zhang, Xing Xu, Heng Tao Shen
- 年份：2020
- 出版日期：2020-08-26
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Multimedia
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1520-9210
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tmm.2020.3019710
- OpenAlex ID：https://openalex.org/W3081484346
- 落地页：https://doi.org/10.1109/tmm.2020.3019710
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Image and Video Retrieval Techniques, Domain Adaptation and Few-Shot Learning
- 关键词：Computer science, Modal, Metric (unit), Matching (statistics), Ranking (information retrieval), Weighting, Artificial intelligence, Margin (machine learning), Pattern recognition (psychology), Theory of relativity, Machine learning, Algorithm, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Training under supervision of triplet ranking loss is a dominant methodology for cross-modal matching models, while good-performing losses in this domain are immensely under-explored since the majority of advanced metric losses are inapplicable due to the particularity of cross-modal setting. Current prominent approaches of metric learning have developed various weighting schemes that assign weights to separate positive or negative samples. It is the interclass relative order in a triplet, however, that matters. In this work, we propose a new Interclass-Relativity-Adaptive (IRA) loss that assigns weights to the relative similarities between positive and negative pairs instead of separate pairs, which allows us to regard a whole triplet as a weighable entity and achieve maximum utilization of sole positive under cross-modal setting. Our method outperforms the baselines by a large margin and obtains competitive results on two video-text matching benchmarks and two image-text matching benchmarks. We also further extend our method to two unimodal image retrieval benchmarks to test its generality and achieve new state-of-the-art results.

## 16817. Efficient and sparse neural networks by pruning weights in a multiobjective learning approach

- 标题：Efficient and sparse neural networks by pruning weights in a multiobjective learning approach
- 作者：Malena Reiners, Kathrin Klamroth, Fabian Heldmann, Michael Stiglmayr
- 年份：2022
- 出版日期：2022-01-10
- 类型：article
- 语言：en
- 来源：Computers & Operations Research
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0305-0548
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.cor.2021.105676
- OpenAlex ID：https://openalex.org/W3082139599
- 落地页：https://doi.org/10.1016/j.cor.2021.105676
- 主主题：Stochastic Gradient Optimization Techniques
- 主题：Stochastic Gradient Optimization Techniques, Advanced Neural Network Applications, Adversarial Robustness in Machine Learning
- 关键词：Overfitting, Computer science, Mathematical optimization, Pruning, Multi-objective optimization, Artificial intelligence, Artificial neural network, Machine learning, Cross entropy, Computational complexity theory, Benchmark (surveying), Mathematics, Algorithm, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16818. Understanding adversarial robustness via critical attacking route

- 标题：Understanding adversarial robustness via critical attacking route
- 作者：Tianlin Li, Aishan Liu, Xianglong Liu, Yitao Xu, Chongzhi Zhang, Xiaofei Xie
- 年份：2020
- 出版日期：2020-08-29
- 类型：article
- 语言：en
- 来源：Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0255
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.ins.2020.08.043
- OpenAlex ID：https://openalex.org/W3082949018
- 落地页：https://doi.org/10.1016/j.ins.2020.08.043
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Bacillus and Francisella bacterial research
- 关键词：Adversarial system, Robustness (evolution), Computer science, Deep neural networks, Artificial intelligence, Rumor, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep neural networks (DNNs) are vulnerable to adversarial examples which are generated by inputs with imperceptible perturbations. Understanding adversarial robustness of DNNs has become an important issue, which would for certain result in better practical deep learning applications. To address this issue, we try to explain adversarial robustness for deep models from a new perspective of critical attacking route, which is computed by a gradient-based influence propagation strategy. Similar to rumor spreading in social networks, we believe that adversarial noises are amplified and propagated through the critical attacking route. By exploiting neurons’ influences layer by layer, we compose the critical attacking route with neurons that make the highest contributions towards model decision. In this paper, we first draw the close connection between adversarial robustness and critical attacking route, as the route makes the most non-trivial contributions to model predictions in the adversarial setting. By constraining the propagation process and node behaviors on this route, we could weaken the noise propagation and improve model robustness. Also, we find that critical attacking neurons are useful to evaluate sample adversarial hardness that images with higher stimulus are easier to be perturbed into adversarial examples.

## 16819. Defending Against Multiple and Unforeseen Adversarial Videos

- 标题：Defending Against Multiple and Unforeseen Adversarial Videos
- 作者：Shao-Yuan Lo, Vishal M. Patel
- 年份：2021
- 出版日期：2021-12-29
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tip.2021.3137648
- OpenAlex ID：https://openalex.org/W3086943318
- 落地页：https://doi.org/10.1109/tip.2021.3137648
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications
- 关键词：Adversarial system, Computer science, Robustness (evolution), Artificial intelligence, Bounded function, Machine learning, Pattern recognition (psychology), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Adversarial robustness of deep neural networks has been actively investigated. However, most existing defense approaches are limited to a specific type of adversarial perturbations. Specifically, they often fail to offer resistance to multiple attack types simultaneously, i.e., they lack multi-perturbation robustness. Furthermore, compared to image recognition problems, the adversarial robustness of video recognition models is relatively unexplored. While several studies have proposed how to generate adversarial videos, only a handful of approaches about defense strategies have been published in the literature. In this paper, we propose one of the first defense strategies against multiple types of adversarial videos for video recognition. The proposed method, referred to as MultiBN, performs adversarial training on multiple adversarial video types using multiple independent batch normalization (BN) layers with a learning-based BN selection module. With a multiple BN structure, each BN brach is responsible for learning the distribution of a single perturbation type and thus provides more precise distribution estimations. This mechanism benefits dealing with multiple perturbation types. The BN selection module detects the attack type of an input video and sends it to the corresponding BN branch, making MultiBN fully automatic and allowing end-to-end training. Compared to present adversarial training approaches, the proposed MultiBN exhibits stronger multi-perturbation robustness against different and even unforeseen adversarial video types, ranging from Lp-bounded attacks and physically realizable attacks. This holds true on different datasets and target models. Moreover, we conduct an extensive analysis to study the properties of the multiple BN structure.

## 16820. A Fast Non-Redundant Feature Selection Technique for Text Data

- 标题：A Fast Non-Redundant Feature Selection Technique for Text Data
- 作者：Syed Fawad Hussain, Hafiz Zaheer-Ud-Din Babar, Akhtar Khalil, Rashad Jillani, Muhammad Hanif, Khurram Khurshid
- 年份：2020
- 出版日期：2020-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2020.3028469
- OpenAlex ID：https://openalex.org/W3091628222
- 落地页：https://doi.org/10.1109/access.2020.3028469
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/8948470/09211425.pdf
- 主主题：Text and Document Classification Technologies
- 主题：Text and Document Classification Technologies, Face and Expression Recognition, Machine Learning and Data Classification
- 关键词：Feature selection, Discriminative model, Computer science, Artificial intelligence, Mutual information, Pattern recognition (psychology), Classifier (UML), Redundancy (engineering), Robustness (evolution), Feature (linguistics), Minimum redundancy feature selection, Data mining, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Feature selection is critical in reducing the size of data and improving classifier accuracy by selecting an optimum subset of the overall features. Traditionally, each feature is given a score against a particular category (such as using Mutual Information) and the task of feature selection comes down to choosing the top $k$ ranked features with the best average score across all categories. However, this approach has two major drawbacks. Firstly, the maximum or average score of a feature with a class might not necessarily determine its discriminating strength among samples of other classes. Secondly, most feature selection methods only use the scores to select the discriminating features from the corpus without taking into account the redundancy of information provided by the selected features. In this paper, we propose a new feature ranking score measure called the Discriminative Mutual Information (DMI) score. This score helps to select features that distinguish samples of one category against all other categories. Moreover, Non-Redundant Feature Selection (NRFS) heuristic is also proposed that explicitly takes the problem of feature redundancy into account when selecting the features set. The performance of our approach is investigated and compared with other feature selection techniques on datasets derived from high-dimensional text corpora using multiple classification algorithms. The results show that the proposed method leads to better classification micro-F1 score as compared to other state-of-the-art methods. In particular, the proposed method shows great improvement when the number of selected features are small as well as an overall higher robustness to label noise.

## 16821. Calculating LRs for presence of body fluids from mRNA assay data in mixtures

- 标题：Calculating LRs for presence of body fluids from mRNA assay data in mixtures
- 作者：Rolf J.F. Ypma, Petra Anna Maaskant van Wijk, Richard D. Gill, Marjan Sjerps, M. van den Berge
- 年份：2021
- 出版日期：2021-01-18
- 类型：article
- 语言：en
- 来源：Forensic Science International Genetics
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1872-4973
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.fsigen.2020.102455
- OpenAlex ID：https://openalex.org/W3120718634
- 落地页：https://doi.org/10.1016/j.fsigen.2020.102455
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Machine Learning and Algorithms, Algorithms and Data Compression
- 关键词：Computer science, Body fluid, Probabilistic logic, Robustness (evolution), In silico, Classifier (UML), Construct (python library), Artificial intelligence, Statistical model, Data mining, Machine learning, Biological system, Chemistry, Biology, Pathology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16822. Multi-GPU approach to global induction of classification trees for large-scale data mining

- 标题：Multi-GPU approach to global induction of classification trees for large-scale data mining
- 作者：Krzysztof Jurczuk, Marcin Czajkowski, Marek Krętowski
- 年份：2021
- 出版日期：2021-01-14
- 类型：article
- 语言：en
- 来源：Applied Intelligence
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0924-669X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s10489-020-01952-5
- OpenAlex ID：https://openalex.org/W3120934634
- 落地页：https://doi.org/10.1007/s10489-020-01952-5
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s10489-020-01952-5.pdf
- 主主题：Evolutionary Algorithms and Applications
- 主题：Evolutionary Algorithms and Applications, Metaheuristic Optimization Algorithms Research, Machine Learning and Data Classification
- 关键词：Computer science, Speedup, Scalability, CUDA, Evolutionary algorithm, Tree (set theory), Parallel computing, Data mining, Machine learning, Database
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract This paper concerns the evolutionary induction of decision trees (DT) for large-scale data. Such a global approach is one of the alternatives to the top-down inducers. It searches for the tree structure and tests simultaneously and thus gives improvements in the prediction and size of resulting classifiers in many situations. However, it is the population-based and iterative approach that can be too computationally demanding to apply for big data mining directly. The paper demonstrates that this barrier can be overcome by smart distributed/parallel processing. Moreover, we ask the question whether the global approach can truly compete with the greedy systems for large-scale data. For this purpose, we propose a novel multi-GPU approach. It incorporates the knowledge of global DT induction and evolutionary algorithm parallelization together with efficient utilization of memory and computing GPU’s resources. The searches for the tree structure and tests are performed simultaneously on a CPU, while the fitness calculations are delegated to GPUs. Data-parallel decomposition strategy and CUDA framework are applied. Experimental validation is performed on both artificial and real-life datasets. In both cases, the obtained acceleration is very satisfactory. The solution is able to process even billions of instances in a few hours on a single workstation equipped with 4 GPUs. The impact of data characteristics (size and dimension) on convergence and speedup of the evolutionary search is also shown. When the number of GPUs grows, nearly linear scalability is observed what suggests that data size boundaries for evolutionary DT mining are fading.

## 16823. Transductive Semisupervised Deep Hashing

- 标题：Transductive Semisupervised Deep Hashing
- 作者：Weiwei Shi, Yihong Gong, Badong Chen, Xinhong Hei
- 年份：2021
- 出版日期：2021-02-08
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks and Learning Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2162-237X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tnnls.2021.3054386
- OpenAlex ID：https://openalex.org/W3127270411
- 落地页：https://doi.org/10.1109/tnnls.2021.3054386
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Advanced Neural Network Applications, Multimodal Machine Learning Applications
- 关键词：Artificial intelligence, Margin (machine learning), Computer science, Hash function, Convolutional neural network, Pattern recognition (psychology), Deep learning, Regularization (linguistics), Sample (material), Deep neural networks, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep hashing methods have shown their superiority to traditional ones. However, they usually require a large amount of labeled training data for achieving high retrieval accuracies. We propose a novel transductive semisupervised deep hashing (TSSDH) method which is effective to train deep convolutional neural network (DCNN) models with both labeled and unlabeled training samples. TSSDH method consists of the following four main ingredients. First, we extend the traditional transductive learning (TL) principle to make it applicable to DCNN-based deep hashing. Second, we introduce confidence levels for unlabeled samples to reduce adverse effects from uncertain samples. Third, we employ a Gaussian likelihood loss for hash code learning to sufficiently penalize large Hamming distances for similar sample pairs. Fourth, we design the large-margin feature (LMF) regularization to make the learned features satisfy that the distances of similar sample pairs are minimized and the distances of dissimilar sample pairs are larger than a predefined margin. Comprehensive experiments show that the TSSDH method can produce superior image retrieval accuracies compared to the representative semisupervised deep hashing methods under the same number of labeled training samples.

## 16824. Video action detection by learning graph-based spatio-temporal interactions

- 标题：Video action detection by learning graph-based spatio-temporal interactions
- 作者：Matteo Tomei, Lorenzo Baraldi, Simone Calderara, Simone Bronzin, Rita Cucchiara
- 年份：2021
- 出版日期：2021-02-27
- 类型：article
- 语言：en
- 来源：Computer Vision and Image Understanding
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1077-3142
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.cviu.2021.103187
- OpenAlex ID：https://openalex.org/W3134906819
- 落地页：https://doi.org/10.1016/j.cviu.2021.103187
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Anomaly Detection Techniques and Applications, Multimodal Machine Learning Applications
- 关键词：Computer science, CLIPS, Robustness (evolution), Action recognition, Artificial intelligence, Graph, Object detection, Code (set theory), Machine learning, Pattern recognition (psychology), Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Action Detection is a complex task that aims to detect and classify human actions in video clips. Typically, it has been addressed by processing fine-grained features extracted from a video classification backbone. Recently, thanks to the robustness of object and people detectors, a deeper focus has been added on relationship modeling. Following this line, we propose a graph-based framework to learn high-level interactions between people and objects, in both space and time. In our formulation, spatio-temporal relationships are learned through self-attention on a multi-layer graph structure which can connect entities from consecutive clips, thus considering long-range spatial and temporal dependencies. The proposed module is backbone independent by design and does not require end-to-end training. Extensive experiments are conducted on the AVA dataset, where our model demonstrates state-of-the-art results and consistent improvements over baselines built with different backbones. Code is publicly available at https://github.com/aimagelab/STAGE_action_detection.

## 16825. AI World Cup: Robot-Soccer-Based Competitions

- 标题：AI World Cup: Robot-Soccer-Based Competitions
- 作者：Chansol Hong, Inbae Jeong, Luiz Felipe Vecchietti, Dongsoo Har, Jong-Hwan Kim
- 年份：2021
- 出版日期：2021-03-11
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Games
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2475-1502
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tg.2021.3065410
- OpenAlex ID：https://openalex.org/W3138971305
- 落地页：https://doi.org/10.1109/tg.2021.3065410
- 主主题：Artificial Intelligence in Games
- 主题：Artificial Intelligence in Games, Multimodal Machine Learning Applications, Reinforcement Learning in Robotics
- 关键词：Artificial intelligence, Robot, Competition (biology), Computer science, Applications of artificial intelligence, Set (abstract data type), Robotics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Games have been used as excellent testbeds for research on artificial intelligence (AI) and computational intelligence for their diversity and complexity. In this article, we present AI World Cup, a set of AI competitions based on the game of soccer. We provide an introduction to the three challenges that concern a robot soccer match using both value-based and image-based state representations. AI Soccer runs the robot soccer match by participants managing each team of five two-wheeled robots. AI Commentator and AI Reporter observe the AI Soccer match and output real-time commentary and a summary article, respectively. Also, we introduce the AI World Cup platform along with rationale behind notable design choices. The official international AI World Cups held in 2018 and 2019 and the AI Masters competition held in 2019 as a part of the World Cyber Games are briefly discussed. Technical aspects of the strategies developed by participants are also discussed.

## 16826. Probabilistic robustness estimates for feed-forward neural networks

- 标题：Probabilistic robustness estimates for feed-forward neural networks
- 作者：Nicolas Couëllan
- 年份：2021
- 出版日期：2021-05-14
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.neunet.2021.04.037
- OpenAlex ID：https://openalex.org/W3160683869
- 落地页：https://doi.org/10.1016/j.neunet.2021.04.037
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Probabilistic and Robust Engineering Design, Nuclear reactor physics and engineering
- 关键词：Robustness (evolution), Computer science, Artificial neural network, Probabilistic logic, Convolutional neural network, Exploit, Artificial intelligence, Probabilistic neural network, Machine learning, Algorithm, Time delay neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16827. Iterative graph attention memory network for cross-modal retrieval

- 标题：Iterative graph attention memory network for cross-modal retrieval
- 作者：Xinfeng Dong, Huaxiang Zhang, Xiao Dong, Xu Lu
- 年份：2021
- 出版日期：2021-05-12
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2021.107138
- OpenAlex ID：https://openalex.org/W3161115174
- 落地页：https://doi.org/10.1016/j.knosys.2021.107138
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications, Video Analysis and Summarization
- 关键词：Computer science, Graph, Modal, Artificial intelligence, Discriminative model, Semantics (computer science), Pattern recognition (psychology), Representation (politics), Theoretical computer science, Feature (linguistics), Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16828. Know what you don't need: Single-Shot Meta-Pruning for attention heads

- 标题：Know what you don't need: Single-Shot Meta-Pruning for attention heads
- 作者：Zhengyan Zhang, Fanchao Qi, Zhiyuan Liu, Qun Liu, Maosong Sun
- 年份：2021
- 出版日期：2021-01-01
- 类型：article
- 语言：en
- 来源：AI Open
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2666-6510
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1016/j.aiopen.2021.05.003
- OpenAlex ID：https://openalex.org/W3166574921
- 落地页：https://doi.org/10.1016/j.aiopen.2021.05.003
- 主主题：Topic Modeling
- 主题：Topic Modeling, Natural Language Processing Techniques, Multimodal Machine Learning Applications
- 关键词：Computer science, Transformer, Inference, Pruning, Artificial intelligence, Language model, Machine learning, Deep learning, Focus (optics), Natural language processing, Overhead (engineering), Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Deep pre-trained Transformer models have achieved state-of-the-art results over a variety of natural language processing (NLP) tasks. By learning rich language knowledge with millions of parameters, these models are usually overparameterized and significantly increase the computational overhead in applications. It is intuitive to address this issue by model compression. In this work, we propose a method, called Single-Shot Meta-Pruning, to compress deep pre-trained Transformers before fine-tuning. Specifically, we focus on pruning unnecessary attention heads adaptively for different downstream tasks. To measure the informativeness of attention heads, we train our Single-Shot Meta-Pruner (SMP) with a meta-learning paradigm aiming to maintain the distribution of text representations after pruning. Compared with existing compression methods for pre-trained models, our method can reduce the overhead of both fine-tuning and inference. Experimental results show that our pruner can selectively prune 50% of attention heads with little impact on the performance on downstream tasks and even provide better text representations. The source code is available at https://github.com/thunlp/SMP.

## 16829. Irony: Context accessibility and processing effort

- 标题：Irony: Context accessibility and processing effort
- 作者：Francisco Yus Ramos
- 年份：1997
- 出版日期：1997-01-01
- 类型：article
- 语言：en
- 来源：Pragmalinguistica
- 来源类型：journal
- 出版方：University of Cádiz
- ISSN-L：1133-682X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：diamond
- DOI：10.25267/pragmalinguistica.1997.i5.17
- OpenAlex ID：https://openalex.org/W4239763114
- 落地页：http://doi.org/10.25267/pragmalinguistica.1997.i5.17
- 主主题：Online Learning and Analytics
- 主题：Online Learning and Analytics, Multimodal Machine Learning Applications
- 关键词：Irony, Context (archaeology), Computer science, Human–computer interaction, Linguistics, Geography, Philosophy
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Irony is considered a discursive strategy in which the literal sense of an utterance differs from its real interpretation, that is, the one intended by the sender. Therefore, irony is labelled as an indirect utterance, and is said to be more difficult to process than literal utterances. In this article a principle of optimal accessibility lo irony is proposed, which is motivated by the attempt to shed light on the validity or incorrection of this argument.

## 16830. Accelerating generalized linear models with MLWeaving

- 标题：Accelerating generalized linear models with MLWeaving
- 作者：Zeke Wang, Kaan Kara, Hantian Zhang, Gustavo Alonso, Onur Mutlu, Ce Zhang
- 年份：2019
- 出版日期：2019-03-01
- 类型：article
- 语言：en
- 来源：Proceedings of the VLDB Endowment
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：2150-8097
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.14778/3317315.3317322
- OpenAlex ID：https://openalex.org/W4288487491
- 落地页：https://doi.org/10.14778/3317315.3317322
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Machine Learning and Algorithms, Error Correcting Code Techniques
- 关键词：Computer science, Quantization (signal processing), Acceleration, Algorithm, Implementation, Gradient descent, Computer engineering, External Data Representation, Stochastic gradient descent, Benchmark (surveying), Theoretical computer science, Artificial intelligence, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Learning from the data stored in a database is an important function increasingly available in relational engines. Methods using lower precision input data are of special interest given their overall higher efficiency. However, in databases, these methods have a hidden cost: the quantization of the real value into a smaller number is an expensive step. To address this issue, we present ML-Weaving, a data structure and hardware acceleration technique intended to speed up learning of generalized linear models over low precision data. MLWeaving provides a compact in-memory representation that enables the retrieval of data at any level of precision. MLWeaving also provides a highly efficient implementation of stochastic gradient descent on FPGAs and enables the dynamic tuning of precision, instead of using a fixed precision level during learning. Experimental results show that MLWeaving converges up to 16 x faster than low-precision implementations of first-order methods on CPUs.

## 16831. Flexible Bayesian Modelling for Survival Data

- 标题：Flexible Bayesian Modelling for Survival Data
- 作者：Paul Gustafson
- 年份：1998
- 出版日期：1998-08-01
- 类型：article
- 语言：en
- 来源：Lifetime Data Analysis
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1380-7870
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1023/a:1009673932333
- OpenAlex ID：https://openalex.org/W64046661
- 落地页：https://doi.org/10.1023/a:1009673932333
- 主主题：Statistical Methods and Inference
- 主题：Statistical Methods and Inference, Statistical Methods and Bayesian Inference, Machine Learning and Data Classification
- 关键词：Covariate, Econometrics, Bayesian probability, Hazard, Additive function, Mathematics, Bayes' theorem, Proportional hazards model, Hierarchical database model, Variable (mathematics), Computer science, Statistics, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16832. Instance-based concept learning from multiclass DNA microarray data

- 标题：Instance-based concept learning from multiclass DNA microarray data
- 作者：Daniel Berrar, Ian Bradbury, Werner Dubitzky
- 年份：2006
- 出版日期：2006-02-16
- 类型：article
- 语言：en
- 来源：BMC Bioinformatics
- 来源类型：journal
- 出版方：BioMed Central
- ISSN-L：1471-2105
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1186/1471-2105-7-73
- OpenAlex ID：https://openalex.org/W1561789977
- 落地页：https://doi.org/10.1186/1471-2105-7-73
- 开放 PDF 链接：https://bmcbioinformatics.biomedcentral.com/counter/pdf/10.1186/1471-2105-7-73
- 主主题：Gene expression and cancer classification
- 主题：Gene expression and cancer classification, Imbalanced Data Classification Techniques, Machine Learning and Data Classification
- 关键词：Computer science, Artificial intelligence, Resampling, Machine learning, Classifier (UML), Data mining, Statistical hypothesis testing, DNA microarray, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
BACKGROUND: Various statistical and machine learning methods have been successfully applied to the classification of DNA microarray data. Simple instance-based classifiers such as nearest neighbor (NN) approaches perform remarkably well in comparison to more complex models, and are currently experiencing a renaissance in the analysis of data sets from biology and biotechnology. While binary classification of microarray data has been extensively investigated, studies involving multiclass data are rare. The question remains open whether there exists a significant difference in performance between NN approaches and more complex multiclass methods. Comparative studies in this field commonly assess different models based on their classification accuracy only; however, this approach lacks the rigor needed to draw reliable conclusions and is inadequate for testing the null hypothesis of equal performance. Comparing novel classification models to existing approaches requires focusing on the significance of differences in performance. RESULTS: We investigated the performance of instance-based classifiers, including a NN classifier able to assign a degree of class membership to each sample. This model alleviates a major problem of conventional instance-based learners, namely the lack of confidence values for predictions. The model translates the distances to the nearest neighbors into 'confidence scores'; the higher the confidence score, the closer is the considered instance to a pre-defined class. We applied the models to three real gene expression data sets and compared them with state-of-the-art methods for classifying microarray data of multiple classes, assessing performance using a statistical significance test that took into account the data resampling strategy. Simple NN classifiers performed as well as, or significantly better than, their more intricate competitors. CONCLUSION: Given its highly intuitive underlying principles--simplicity, ease-of-use, and robustness--the k-NN classifier complemented by a suitable distance-weighting regime constitutes an excellent alternative to more complex models for multiclass microarray data sets. Instance-based classifiers using weighted distances are not limited to microarray data sets, but are likely to perform competitively in classifications of high-dimensional biological data sets such as those generated by high-throughput mass spectrometry.

## 16833. PROTOTYPE CLASSIFIER DESIGN WITH PRUNING

- 标题：PROTOTYPE CLASSIFIER DESIGN WITH PRUNING
- 作者：Li Jiang, M.T. Manry, Changhua Yu, D.R. Wilson
- 年份：2005
- 出版日期：2005-02-01
- 类型：article
- 语言：en
- 来源：International Journal of Artificial Intelligence Tools
- 来源类型：journal
- 出版方：World Scientific
- ISSN-L：0218-2130
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1142/s0218213005002090
- OpenAlex ID：https://openalex.org/W1971247125
- 落地页：https://doi.org/10.1142/s0218213005002090
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Machine Learning and Data Classification, Face and Expression Recognition
- 关键词：Computer science, Learning vector quantization, Classifier (UML), Speedup, Linde–Buzo–Gray algorithm, Algorithm, Vector quantization, Pruning, Artificial intelligence, k-nearest neighbors algorithm, Machine learning, Parallel computing
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Algorithms reducing the storage requirement of the nearest neighbor classifier (NNC) can be divided into three main categories: Fast searching algorithms, Instance-based learning algorithms and Prototype based algorithms. We propose an algorithm, LVQPRU, for pruning NNC prototype vectors and a compact classifier with good performance is obtained. The basic condensing algorithm is applied to the initial prototypes to speed up the learning process. The learning vector quantization (LVQ) algorithm is utilized to fine tune the remaining prototypes during each pruning iteration. We evaluate LVQPRU on several data sets along with 12 other algorithms using ten-fold cross-validation. Simulation results show that the proposed algorithm has high generalization accuracy and good storage reduction ratios.

## 16834. Supervised projection approach for boosting classifiers

- 标题：Supervised projection approach for boosting classifiers
- 作者：Nicolás García‐Pedrajas
- 年份：2009
- 出版日期：2009-01-07
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2008.12.023
- OpenAlex ID：https://openalex.org/W1989617935
- 落地页：https://doi.org/10.1016/j.patcog.2008.12.023
- 主主题：Water Systems and Optimization
- 主题：Water Systems and Optimization, Anomaly Detection Techniques and Applications, Machine Learning and Data Classification
- 关键词：Boosting (machine learning), Artificial intelligence, AdaBoost, Outlier, Pattern recognition (psychology), Classifier (UML), Computer science, Maximization, Weighting, Machine learning, Binary classification, Mathematics, Support vector machine, Mathematical optimization
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16835. ASN-minimax double sampling plans for variables

- 标题：ASN-minimax double sampling plans for variables
- 作者：Benno Feldmann, Wolf Krumbholz
- 年份：2002
- 出版日期：2002-07-01
- 类型：article
- 语言：en
- 来源：Statistical Papers
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0932-5026
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00362-002-0110-2
- OpenAlex ID：https://openalex.org/W1990188184
- 落地页：https://doi.org/10.1007/s00362-002-0110-2
- 主主题：Advanced Statistical Process Monitoring
- 主题：Advanced Statistical Process Monitoring, Machine Learning and Algorithms, Statistical Methods and Inference
- 关键词：Minimax, Mathematics, Limit (mathematics), Exponential function, Sampling (signal processing), Exponential distribution, Plan (archaeology), Sample size determination, Distribution (mathematics), Normal distribution, Sample (material), Applied mathematics, Statistics, Combinatorics, Mathematical optimization, Discrete mathematics, Computer science, Mathematical analysis
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16836. Programs over semigroups of dot-depth one

- 标题：Programs over semigroups of dot-depth one
- 作者：Alexis Maciel, Pierre Péladeau, Denis Thérien
- 年份：2000
- 出版日期：2000-08-01
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/s0304-3975(99)00278-9
- OpenAlex ID：https://openalex.org/W1996359785
- 落地页：https://doi.org/10.1016/s0304-3975(99)00278-9
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Complexity and Algorithms in Graphs, Machine Learning and Algorithms
- 关键词：Assertion, Mathematics, Variety (cybernetics), Algebraic number, Discrete mathematics, Boolean function, Circuit complexity, Boolean circuit, Semigroup, Algebra over a field, Pure mathematics, Electronic circuit, Computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16837. ON THE BURNSIDE SEMIGROUPS x<sup>n</sup> = x<sup>n+m</sup>

- 标题：ON THE BURNSIDE SEMIGROUPS x<sup>n</sup> = x<sup>n+m</sup>
- 作者：Alair Pereira do Lago
- 年份：1996
- 出版日期：1996-04-01
- 类型：article
- 语言：en
- 来源：International Journal of Algebra and Computation
- 来源类型：journal
- 出版方：World Scientific
- ISSN-L：0218-1967
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1142/s0218196796000106
- OpenAlex ID：https://openalex.org/W1996553418
- 落地页：https://doi.org/10.1142/s0218196796000106
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Natural Language Processing Techniques, Machine Learning and Algorithms
- 关键词：Mathematics, Semigroup, Conjecture, Combinatorics, Generator (circuit theory), Congruence (geometry), Order (exchange), Elementary proof, Discrete mathematics, Geometry
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this paper we prove that the congruence classes of A* associated to the Burnside semigroup with |A| generators defined by the equation x n =x n+m , for n≥4 and m≥1, are recognizable. This problem was originally formulated by Brzozowski in 1969 for m=1 and n≥2. De Luca and Varricchio solved the problem for n≥5 in 90. A little later, McCammond extended the problem for m≥1 and solved it independently in the cases n≥6 and m≥1. Our work, which is based on the techniques developed by de Luca and Varricchio, extends both these results. We effectively construct a minimal generator Σ of our congruence. We introduce an elementary concept, namely the stability of productions, which allows to eliminate all hypothesis related to the values of n and m. A substantial part of our proof consists of showing that all productions in Σ are stable, for n≥4 and m≥1. We also show that Σ is a Church-Rosser rewriting system, thus solving the word problem, and show that the semigroup is finite [Formula: see text]-above. We prove that the frame of the ℛ-classes of the semigroup is a tree. We characterize and calculate the ℛ-classes, ℋ-classes and the [Formula: see text]-classes of the semigroup, regular or not, and prove that its maximal subgroups are cyclic of order m whenever all productions of Σ are stable. Recently Guba extended the cases in which the conjecture holds to n≥3 and m≥1. Using his work we obtain the stability of the productions of Σ for n=3 and m≥1 too and, hence, all properties about the semigroup structure hold in this case.

## 16838. Laplacian unit-hyperplane learning from positive and unlabeled examples

- 标题：Laplacian unit-hyperplane learning from positive and unlabeled examples
- 作者：Yuan‐Hai Shao, Wei-Jie Chen, Liming Liu, Nai-Yang Deng
- 年份：2015
- 出版日期：2015-04-05
- 类型：article
- 语言：en
- 来源：Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0255
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ins.2015.03.066
- OpenAlex ID：https://openalex.org/W2016317391
- 落地页：https://doi.org/10.1016/j.ins.2015.03.066
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Imbalanced Data Classification Techniques, Machine Learning and Algorithms
- 关键词：Hyperplane, Maximization, Classifier (UML), Computation, Computer science, Discriminant, Artificial intelligence, Margin (machine learning), Support vector machine, Mathematics, Laplace operator, Quadratic equation, Machine learning, Algorithm, Mathematical optimization, Combinatorics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16839. Learning intersections of halfspaces with a margin

- 标题：Learning intersections of halfspaces with a margin
- 作者：Adam R. Klivans, Rocco A. Servedio
- 年份：2007
- 出版日期：2007-04-26
- 类型：article
- 语言：en
- 来源：Journal of Computer and System Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0022-0000
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.jcss.2007.04.012
- OpenAlex ID：https://openalex.org/W2018199527
- 落地页：https://doi.org/10.1016/j.jcss.2007.04.012
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Domain Adaptation and Few-Shot Learning, Machine Learning and Data Classification
- 关键词：Hyperplane, Margin (machine learning), Mathematics, Simple (philosophy), Polynomial, Function (biology), Projection (relational algebra), Computer science, Exponential time hypothesis, Reduction (mathematics), Exponential growth, Combinatorics, Dimensionality reduction, Exponential function, Curse of dimensionality, Kernel (algebra), Algorithm, Time complexity, Artificial intelligence, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16840. Multi-selection of instances: A straightforward way to improve evolutionary instance selection

- 标题：Multi-selection of instances: A straightforward way to improve evolutionary instance selection
- 作者：Nicolás García‐Pedrajas, Javier Pérez-Rodríguez
- 年份：2012
- 出版日期：2012-07-06
- 类型：article
- 语言：en
- 来源：Applied Soft Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1568-4946
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.asoc.2012.06.013
- OpenAlex ID：https://openalex.org/W2024847174
- 落地页：https://doi.org/10.1016/j.asoc.2012.06.013
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Imbalanced Data Classification Techniques, Data Stream Mining Techniques
- 关键词：Computer science, Selection (genetic algorithm), Machine learning, Artificial intelligence, Classifier (UML), Evolutionary algorithm, Task (project management), Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16841. Learning acceptable windows of contingency

- 标题：Learning acceptable windows of contingency
- 作者：Kevin Gold, Brian Scassellati
- 年份：2006
- 出版日期：2006-06-01
- 类型：article
- 语言：en
- 来源：Connection Science
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0954-0091
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1080/09540090600768435
- OpenAlex ID：https://openalex.org/W2029611868
- 落地页：https://doi.org/10.1080/09540090600768435
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Computability, Logic, AI Algorithms, Reinforcement Learning in Robotics
- 关键词：Computer science, Poisson distribution, Action (physics), Robot, Contingency, Interval (graph theory), Range (aeronautics), Artificial intelligence, Algorithm, Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
By learning a range of possible times over which the effect of an action can take place, a robot can reason more effectively about causal and contingent relationships in the world. An algorithm is presented for learning the interval of possible times during which a response to an action can take place. The algorithm was implemented on a physical robot for the domains of visual self-recognition and auditory social-partner recognition. The environment model assumes that natural environments generate Poisson distributions of random events at all scales. A linear-time algorithm called Poisson threshold learning can generate a threshold T that provides an arbitrarily small rate of background events λ (T), if such a threshold exists for the specified error rate.

## 16842. Learning Probabilistic Automata and Markov Chains via Queries

- 标题：Learning Probabilistic Automata and Markov Chains via Queries
- 作者：Wen-Guey Tzeng
- 年份：1992
- 出版日期：1992-03-01
- 类型：article
- 语言：en
- 来源：Machine Learning
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-6125
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1023/a:1022616503659
- OpenAlex ID：https://openalex.org/W2035364689
- 落地页：https://doi.org/10.1023/a:1022616503659
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1023/A:1022616503659.pdf
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Optimization and Search Problems, semigroups and automata theory
- 关键词：Markov chain, Probabilistic logic, Quantum finite automata, Probabilistic automaton, Computer science, Theoretical computer science, Learning automata, Probabilistic CTL, Automaton, Automata theory, Algorithm, Artificial intelligence, Probabilistic analysis of algorithms, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16843. New balanced sampling plans excluding adjacent units

- 标题：New balanced sampling plans excluding adjacent units
- 作者：James H. Wright, John Stufken
- 年份：2008
- 出版日期：2008-03-17
- 类型：article
- 语言：en
- 来源：Journal of Statistical Planning and Inference
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0378-3758
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.jspi.2006.10.020
- OpenAlex ID：https://openalex.org/W2043680716
- 落地页：https://doi.org/10.1016/j.jspi.2006.10.020
- 主主题：graph theory and CDMA systems
- 主题：graph theory and CDMA systems, Optimal Experimental Design Methods, Machine Learning and Algorithms
- 关键词：Mathematics, Sampling (signal processing), Statistics, Sampling design, Sample (material), Inference, Order (exchange), Selection (genetic algorithm), Combinatorics, Computer science, Population, Demography
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16844. Learning Monotone Log-Term DNF Formulas under the Uniform Distribution

- 标题：Learning Monotone Log-Term DNF Formulas under the Uniform Distribution
- 作者：Yoshifumi Sakai, Akira Maruoka
- 年份：2000
- 出版日期：2000-01-02
- 类型：article
- 语言：en
- 来源：Theory of Computing Systems
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1432-4350
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s002249910002
- OpenAlex ID：https://openalex.org/W2043842763
- 落地页：https://doi.org/10.1007/s002249910002
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Imbalanced Data Classification Techniques, Algorithms and Data Compression
- 关键词：Learnability, Monotone polygon, Term (time), Mathematics, Binary logarithm, Combinatorics, Class (philosophy), Log-log plot, Polynomial, Discrete mathematics, Disjunctive normal form, Distribution (mathematics), Time complexity, Concept class, Computer science, Artificial intelligence, Mathematical analysis
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16845. A DNA computer model for solving vertex coloring problem

- 标题：A DNA computer model for solving vertex coloring problem
- 作者：Jin Xu, Xiaoli Qiang, Fang Gang, Kang Zhou
- 年份：2006
- 出版日期：2006-10-01
- 类型：article
- 语言：en
- 来源：Chinese Science Bulletin
- 来源类型：journal
- 出版方：Springer Nature
- ISSN-L：1001-6538
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11434-006-2145-6
- OpenAlex ID：https://openalex.org/W2052167064
- 落地页：https://doi.org/10.1007/s11434-006-2145-6
- 主主题：DNA and Biological Computing
- 主题：DNA and Biological Computing, Advanced biosensing and bioanalysis techniques, Machine Learning and Algorithms
- 关键词：Vertex (graph theory), DNA computing, DNA, Polyacrylamide gel electrophoresis, Complete coloring, Computer science, Polyacrylamide, Combinatorics, Graph, Gel electrophoresis, Algorithm, Mathematics, Chemistry, Theoretical computer science, Biology, Molecular biology, Genetics, Computation, Biochemistry, Graph power
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16846. Learning decision trees with taxonomy of propositionalized attributes

- 标题：Learning decision trees with taxonomy of propositionalized attributes
- 作者：Dae-Ki Kang, Kiwook Sohn
- 年份：2008
- 出版日期：2008-07-24
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2008.07.009
- OpenAlex ID：https://openalex.org/W2056959138
- 落地页：https://doi.org/10.1016/j.patcog.2008.07.009
- 主主题：Data Mining Algorithms and Applications
- 主题：Data Mining Algorithms and Applications, Imbalanced Data Classification Techniques, Machine Learning and Data Classification
- 关键词：Taxonomy (biology), Decision tree, Computer science, Artificial intelligence, Machine learning, Decision tree learning, Class (philosophy), Data mining, Ecology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16847. CLASS PREDICTION OF CANCER USING PROBABILISTIC NEURAL NETWORKS AND RELATIVE CORRELATION METRIC

- 标题：CLASS PREDICTION OF CANCER USING PROBABILISTIC NEURAL NETWORKS AND RELATIVE CORRELATION METRIC
- 作者：Chenn‐Jung Huang
- 年份：2004
- 出版日期：2004-02-01
- 类型：article
- 语言：en
- 来源：Applied Artificial Intelligence
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0883-9514
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1080/08839510490278916
- OpenAlex ID：https://openalex.org/W2066391875
- 落地页：https://doi.org/10.1080/08839510490278916
- 开放 PDF 链接：https://www.tandfonline.com/doi/pdf/10.1080/08839510490278916?download=true
- 主主题：Gene expression and cancer classification
- 主题：Gene expression and cancer classification, Machine Learning and Data Classification, AI in cancer detection
- 关键词：Computer science, Feature selection, Artificial intelligence, Probabilistic logic, Artificial neural network, Correlation, Pattern recognition (psychology), Probabilistic neural network, Metric (unit), Machine learning, Selection (genetic algorithm), Probabilistic classification, Data mining, Class (philosophy), Support vector machine, Time delay neural network, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Accurate diagnosis and classification is the key issue for the optimal treatment of cancer patients.Several studies demonstrate that cancer classification can be estimated with high accuracy, sensitivity, and specificity from microarray-based gene expression profiling using artificial neural networks.In this paper, a comprehensive study was undertaken to investigate the capability of the probabilistic neural networks along with a feature selection method in the application of cancer classification.The feature selection method is based on the correlation with the class distinction.The experimental results show that the conjugation of the probabilistic neural network and the feature selection method can achieve 100% recognition accuracy in the ALL=AML classification, and also attain satisfactory results in two colon cancer data sets.Successful cancer treatment depends on choosing the right regimen for a given patient.How to diagnose cancer subtypes accurately becomes one of the biggest challenges in clinical cancer research since separate treatment strategies are adopted for different tumors.A recent study reported by Golub et al. (1999;Slonim et al. 2000), the first microarray-based and bioinformaticorientated approach for identifying and classifying tumor types, moves cancer diagnosis away from traditional visually based systems to molecular-based systems.They employed a correlation metric to extract a small set of genes and developed a scheme named weighted voting to distinguish acute lymphoblastic leukemia (ALL) from acute myeloid leukemia (AML); the recognition rate they obtained was 94.1%.Motivated by the report of Golub et al. (1999), several algorithms have been proposed to analyze publicly accessible data sets on cancer research in

## 16848. BYY Harmony Learning on Finite Mixture: Adaptive Gradient Implementation and A Floating RPCL Mechanism

- 标题：BYY Harmony Learning on Finite Mixture: Adaptive Gradient Implementation and A Floating RPCL Mechanism
- 作者：Jinwen Ma, Le Wang
- 年份：2006
- 出版日期：2006-08-01
- 类型：article
- 语言：en
- 来源：Neural Processing Letters
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1370-4621
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11063-006-9008-7
- OpenAlex ID：https://openalex.org/W2066545179
- 落地页：https://doi.org/10.1007/s11063-006-9008-7
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Advanced Control Systems Optimization, Neural Networks and Applications
- 关键词：Artificial intelligence, Computer science, Competitive learning, Unsupervised learning, Adaptive learning, Pattern recognition (psychology), Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16849. A Slight Sharpening of LMN

- 标题：A Slight Sharpening of LMN
- 作者：Johan Håstad
- 年份：2001
- 出版日期：2001-11-01
- 类型：article
- 语言：en
- 来源：Journal of Computer and System Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0022-0000
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1006/jcss.2001.1803
- OpenAlex ID：https://openalex.org/W2070540961
- 落地页：https://doi.org/10.1006/jcss.2001.1803
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Complexity and Algorithms in Graphs, Low-power high-performance VLSI design
- 关键词：Sharpening, Argument (complex analysis), Bounded function, Mathematics, Function (biology), Fourier transform, Discrete mathematics, Combinatorics, Algorithm, Computer science, Mathematical analysis, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16850. Robust nonparametric estimation via wavelet median regression

- 标题：Robust nonparametric estimation via wavelet median regression
- 作者：Lawrence D. Brown, T. Tony Cai, Harrison H. Zhou
- 年份：2008
- 出版日期：2008-10-01
- 类型：article
- 语言：en
- 来源：The Annals of Statistics
- 来源类型：journal
- 出版方：Institute of Mathematical Statistics
- ISSN-L：0090-5364
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1214/07-aos513
- OpenAlex ID：https://openalex.org/W2070796287
- 落地页：https://doi.org/10.1214/07-aos513
- 开放 PDF 链接：https://projecteuclid.org/journals/annals-of-statistics/volume-36/issue-5/Robust-nonparametric-estimation-via-wavelet-median-regression/10.1214/07-AOS513.pdf
- 主主题：Statistical Methods and Inference
- 主题：Statistical Methods and Inference, Machine Learning and Algorithms, Advanced Statistical Methods and Models
- 关键词：Estimator, Nonparametric regression, Smoothness, Nonparametric statistics, Minimax, Robust regression, Adaptive estimator, Robust statistics, Wavelet, Quantile regression
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In this paper we develop a nonparametric regression method that is simultaneously adaptive over a wide range of function classes for the regression function and robust over a large collection of error distributions, including those that are heavy-tailed, and may not even possess variances or means. Our approach is to first use local medians to turn the problem of nonparametric regression with unknown noise distribution into a standard Gaussian regression problem and then apply a wavelet block thresholding procedure to construct an estimator of the regression function. It is shown that the estimator simultaneously attains the optimal rate of convergence over a wide range of the Besov classes, without prior knowledge of the smoothness of the underlying functions or prior knowledge of the error distribution. The estimator also automatically adapts to the local smoothness of the underlying function, and attains the local adaptive minimax rate for estimating functions at a point. A key technical result in our development is a quantile coupling theorem which gives a tight bound for the quantile coupling between the sample medians and a normal variable. This median coupling inequality may be of independent interest.

## 16851. Incremental Optimization Mechanism for Constructing a Decision Tree in Data Stream Mining

- 标题：Incremental Optimization Mechanism for Constructing a Decision Tree in Data Stream Mining
- 作者：Hang Yang, Simon Fong
- 年份：2013
- 出版日期：2013-01-01
- 类型：article
- 语言：en
- 来源：Mathematical Problems in Engineering
- 来源类型：journal
- 出版方：Hindawi Publishing Corporation
- ISSN-L：1024-123X
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1155/2013/580397
- OpenAlex ID：https://openalex.org/W2084433447
- 落地页：https://doi.org/10.1155/2013/580397
- 开放 PDF 链接：https://downloads.hindawi.com/journals/mpe/2013/580397.pdf
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Machine Learning and Data Classification, Advanced Control Systems Optimization
- 关键词：Tree (set theory), Overfitting, Computer science, Incremental decision tree, Decision tree, Node (physics), Data mining, Decision tree learning, Data stream, Computation, Mechanism (biology), ID3 algorithm, Algorithm, Machine learning, Artificial intelligence, Mathematical optimization, Mathematics, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Imperfect data stream leads to tree size explosion and detrimental accuracy problems. Overfitting problem and the imbalanced class distribution reduce the performance of the original decision-tree algorithm for stream mining. In this paper, we propose an incremental optimization mechanism to solve these problems. The mechanism is called Optimized Very Fast Decision Tree (OVFDT) that possesses an optimized node-splitting control mechanism. Accuracy, tree size, and the learning time are the significant factors influencing the algorithm’s performance. Naturally a bigger tree size takes longer computation time. OVFDT is a pioneer model equipped with an incremental optimization mechanism that seeks for a balance between accuracy and tree size for data stream mining. It operates incrementally by a test-then-train approach. Three types of functional tree leaves improve the accuracy with which the tree model makes a prediction for a new data stream in the testing phase. The optimized node-splitting mechanism controls the tree model growth in the training phase. The experiment shows that OVFDT obtains an optimal tree structure in both numeric and nominal datasets.

## 16852. On the cut-off point for combinatorial group testing

- 标题：On the cut-off point for combinatorial group testing
- 作者：Paul Fischer, Norbert Klasner, Ingo Wegenera
- 年份：1999
- 出版日期：1999-01-01
- 类型：article
- 语言：en
- 来源：Discrete Applied Mathematics
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0166-218X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/s0166-218x(98)00119-x
- OpenAlex ID：https://openalex.org/W2088027806
- 落地页：https://doi.org/10.1016/s0166-218x(98)00119-x
- 主主题：SARS-CoV-2 detection and testing
- 主题：SARS-CoV-2 detection and testing, Machine Learning and Algorithms, Advanced biosensing and bioanalysis techniques
- 关键词：Mathematics, Combinatorics, Conjecture, Set (abstract data type), Object (grammar), Group (periodic table), Point (geometry), Group testing, Discrete mathematics, Computer science, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16853. Continuous prediction of manufacturing performance throughout the production lifecycle

- 标题：Continuous prediction of manufacturing performance throughout the production lifecycle
- 作者：Sholom M. Weiss, Amit Dhurandhar, Robert J. Baseman, Brian White, R. Logan, J. Winslow, Daniel Poindexter
- 年份：2014
- 出版日期：2014-04-10
- 类型：article
- 语言：en
- 来源：Journal of Intelligent Manufacturing
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0956-5515
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s10845-014-0911-x
- OpenAlex ID：https://openalex.org/W2091629725
- 落地页：https://doi.org/10.1007/s10845-014-0911-x
- 主主题：Industrial Vision Systems and Defect Detection
- 主题：Industrial Vision Systems and Defect Detection, Machine Learning and Data Classification, Manufacturing Process and Optimization
- 关键词：Reliability engineering, Expansive, Production (economics), Wafer fabrication, Manufacturing engineering, Engineering, Product (mathematics), Microprocessor, Population, Task (project management), Computer science, Wafer, Process engineering, Systems engineering, Embedded system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16854. REAL-TIME SPOKEN-LANGUAGE PROGRAMMING FOR COOPERATIVE INTERACTION WITH A HUMANOID APPRENTICE

- 标题：REAL-TIME SPOKEN-LANGUAGE PROGRAMMING FOR COOPERATIVE INTERACTION WITH A HUMANOID APPRENTICE
- 作者：Peter Ford Dominey, Anthony Mallet, Eiichi Yoshida
- 年份：2009
- 出版日期：2009-06-01
- 类型：article
- 语言：en
- 来源：International Journal of Humanoid Robotics
- 来源类型：journal
- 出版方：World Scientific
- ISSN-L：0219-8436
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1142/s0219843609001711
- OpenAlex ID：https://openalex.org/W2116350388
- 落地页：https://doi.org/10.1142/s0219843609001711
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Robot Manipulation and Learning, Natural Language Processing Techniques
- 关键词：Computer science, Executable, Task (project management), Human–computer interaction, Spoken language, USable, Humanoid robot, Flexibility (engineering), Programming by demonstration, Artificial intelligence, Agile software development, Robot, Coarticulation, Domain (mathematical analysis), Programming language, Speech recognition, Software engineering, Multimedia
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
An apprentice is an able-bodied individual that will interactively assist an expert, and through this interaction, acquire knowledge and skill in the given task domain. A humanoid apprentice should have a useful repertoire of sensory-motor acts that the human can command with spoken language, along with a real-time behavioral sequence acquisition ability. The learned sequences should function as executable procedures that can operate in a flexible manner that are not rigidly sensitive to initial conditions. Our study integrates these capabilities in a real-time system on the HRP-2 humanoid, for learning a cooperative assembly task. We previously defined a system for Spoken Language Programming (SLP) that allowed the user to guide the robot through an arbitrary, task relevant, motor sequence via spoken commands, and to store this sequence as re-usable macro. Here, we significantly extend the SPL system: It integrates vision and motion planning into the SLP framework, providing a new level of flexibility in the actions that can be created, and it allows the user to create "generic" functions with arguments (e.g. Give me X), and it allows multiple functions to be created.

## 16855. Correcting the Kullback–Leibler distance for feature selection

- 标题：Correcting the Kullback–Leibler distance for feature selection
- 作者：Frans Coetzee
- 年份：2005
- 出版日期：2005-04-15
- 类型：article
- 语言：en
- 来源：Pattern Recognition Letters
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-8655
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patrec.2005.01.014
- OpenAlex ID：https://openalex.org/W2127994824
- 落地页：https://doi.org/10.1016/j.patrec.2005.01.014
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Machine Learning and Algorithms, Machine Learning and Data Classification
- 关键词：Kullback–Leibler divergence, Mathematics, Feature selection, Feature (linguistics), Function (biology), Separation (statistics), Pattern recognition (psychology), Selection (genetic algorithm), Variance (accounting), Artificial intelligence, Divergence (linguistics), Distance measures, Statistics, Computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16856. Universal automata and NFA learning

- 标题：Universal automata and NFA learning
- 作者：Pedro García, Manuel Vázquez de Parga, Gloria Alvarez, José Ruiz
- 年份：2008
- 出版日期：2008-05-30
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.tcs.2008.05.017
- OpenAlex ID：https://openalex.org/W2131211586
- 落地页：https://doi.org/10.1016/j.tcs.2008.05.017
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, semigroups and automata theory, Algorithms and Data Compression
- 关键词：Automaton, Computer science, Theoretical computer science, Programming language, Mathematics, Artificial intelligence, Discrete mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16857. Analysis of the IJCNN 2007 agnostic learning vs. prior knowledge challenge

- 标题：Analysis of the IJCNN 2007 agnostic learning vs. prior knowledge challenge
- 作者：Isabelle Guyon, Amir Saffari, Gideon Dror, Gavin C. Cawley
- 年份：2007
- 出版日期：2007-12-28
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neunet.2007.12.024
- OpenAlex ID：https://openalex.org/W2133418613
- 落地页：https://doi.org/10.1016/j.neunet.2007.12.024
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Machine Learning and Algorithms, Imbalanced Data Classification Techniques
- 关键词：Computer science, Domain knowledge, Knowledge extraction, Exploit, Feature (linguistics), Smoothing, Machine learning, Feature learning, Domain (mathematical analysis), Data mining, Raw data, Table (database), Artificial intelligence, Information retrieval
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16858. Using beta binomials to estimate classification uncertainty for ensemble models

- 标题：Using beta binomials to estimate classification uncertainty for ensemble models
- 作者：Robert D. Clark, Wenkel Liang, Adam Lee, Michael S. Lawless, Robert Fraczkiewicz, Marvin Waldman
- 年份：2014
- 出版日期：2014-06-21
- 类型：article
- 语言：en
- 来源：Journal of Cheminformatics
- 来源类型：journal
- 出版方：BioMed Central
- ISSN-L：1758-2946
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：gold
- DOI：10.1186/1758-2946-6-34
- OpenAlex ID：https://openalex.org/W2138943567
- 落地页：https://doi.org/10.1186/1758-2946-6-34
- 开放 PDF 链接：https://jcheminf.biomedcentral.com/counter/pdf/10.1186/1758-2946-6-34
- 主主题：Computational Drug Discovery Methods
- 主题：Computational Drug Discovery Methods, Cell Image Analysis Techniques, Machine Learning and Data Classification
- 关键词：Computer science, BETA (programming language), Data mining, Artificial intelligence, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
BACKGROUND: Quantitative structure-activity (QSAR) models have enormous potential for reducing drug discovery and development costs as well as the need for animal testing. Great strides have been made in estimating their overall reliability, but to fully realize that potential, researchers and regulators need to know how confident they can be in individual predictions. RESULTS: Submodels in an ensemble model which have been trained on different subsets of a shared training pool represent multiple samples of the model space, and the degree of agreement among them contains information on the reliability of ensemble predictions. For artificial neural network ensembles (ANNEs) using two different methods for determining ensemble classification - one using vote tallies and the other averaging individual network outputs - we have found that the distribution of predictions across positive vote tallies can be reasonably well-modeled as a beta binomial distribution, as can the distribution of errors. Together, these two distributions can be used to estimate the probability that a given predictive classification will be in error. Large data sets comprised of logP, Ames mutagenicity, and CYP2D6 inhibition data are used to illustrate and validate the method. The distributions of predictions and errors for the training pool accurately predicted the distribution of predictions and errors for large external validation sets, even when the number of positive and negative examples in the training pool were not balanced. Moreover, the likelihood of a given compound being prospectively misclassified as a function of the degree of consensus between networks in the ensemble could in most cases be estimated accurately from the fitted beta binomial distributions for the training pool. CONCLUSIONS: Confidence in an individual predictive classification by an ensemble model can be accurately assessed by examining the distributions of predictions and errors as a function of the degree of agreement among the constituent submodels. Further, ensemble uncertainty estimation can often be improved by adjusting the voting or classification threshold based on the parameters of the error distribution. Finally, the profiles for models whose predictive uncertainty estimates are not reliable provide clues to that effect without the need for comparison to an external test set.

## 16859. A black box for online approximate pattern matching

- 标题：A black box for online approximate pattern matching
- 作者：Raphaël Clifford, Klim Efremenko, Benny Porat, Ely Porat
- 年份：2011
- 出版日期：2011-01-26
- 类型：article
- 语言：en
- 来源：Information and Computation
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0890-5401
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ic.2010.12.007
- OpenAlex ID：https://openalex.org/W2140007524
- 落地页：https://doi.org/10.1016/j.ic.2010.12.007
- 主主题：Algorithms and Data Compression
- 主题：Algorithms and Data Compression, Handwritten Text Recognition Techniques, Machine Learning and Algorithms
- 关键词：Character (mathematics), Hamming distance, Hamming code, Running time, Matching (statistics), Hamming weight, Norm (philosophy), Time complexity, Combinatorics, Computer science, Pattern matching, Algorithm, Online algorithm, Mathematics, Sliding window protocol, Discrete mathematics, Window (computing), Artificial intelligence, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16860. IMPROVING SUPERVISED LEARNING BY SAMPLE DECOMPOSITION

- 标题：IMPROVING SUPERVISED LEARNING BY SAMPLE DECOMPOSITION
- 作者：Lior Rokach, Oded Maimon, Omri Arad
- 年份：2005
- 出版日期：2005-03-01
- 类型：article
- 语言：en
- 来源：International Journal of Computational Intelligence and Applications
- 来源类型：journal
- 出版方：Imperial College Press
- ISSN-L：1469-0268
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1142/s146902680500143x
- OpenAlex ID：https://openalex.org/W2164861862
- 落地页：https://doi.org/10.1142/s146902680500143x
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Machine Learning and Algorithms, Face and Expression Recognition
- 关键词：Computer science, Disjoint sets, Cluster analysis, Classifier (UML), Ensemble learning, Sample complexity, Weighted Majority Algorithm, Tuple, Artificial intelligence, Algorithm, Sample (material), Machine learning, Pattern recognition (psychology), Data mining, Generalization error, Unsupervised learning, Mathematics, Wake-sleep algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This paper introduces a new ensemble technique, cluster-based concurrent decomposition (CBCD) that induces an ensemble of classifiers by decomposing the training set into mutually exclusive sub-samples of equal-size. The CBCD algorithm first clusters the instance space by using the K-means clustering algorithm. Afterwards it produces disjoint sub-samples using the clusters in such a way that each sub-sample is comprised of tuples from all clusters and hence represents the entire dataset. An induction algorithm is applied in turn to each subset, followed by a voting mechanism that combines the classifier's predictions. The CBCD algorithm has two tuning parameters: the number of clusters and the number of subsets to create. Using a suitable meta-learning it is possible to tune these parameters properly. In the experimental study we conducted, the CBCD algorithm, using an embedded C4.5 algorithm, outperformed the bagging algorithm of the same computational complexity.

## 16861. Bayesian Interpretation of a Distance Function for Navigating High-Dimensional Descriptor Spaces

- 标题：Bayesian Interpretation of a Distance Function for Navigating High-Dimensional Descriptor Spaces
- 作者：Martin Vogt, Jeffrey W. Godden, Jürgen Bajorath
- 年份：2006
- 出版日期：2006-12-02
- 类型：article
- 语言：en
- 来源：Journal of Chemical Information and Modeling
- 来源类型：journal
- 出版方：American Chemical Society
- ISSN-L：1549-9596
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1021/ci600280b
- OpenAlex ID：https://openalex.org/W2949492941
- 落地页：https://doi.org/10.1021/ci600280b
- 主主题：Image Retrieval and Classification Techniques
- 主题：Image Retrieval and Classification Techniques, Machine Learning and Algorithms, Face and Expression Recognition
- 关键词：Interpretation (philosophy), Bayesian probability, Function (biology), Artificial intelligence, Mathematics, Computer science, Statistical physics, Physics, Biology, Evolutionary biology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A distance function to analyze molecular similarity relationships in high-dimensional descriptor spaces and focus search calculations on "active subspaces" is defined in Bayesian terms. As a measure of similarity, database compounds are ranked according to their distance from the center of a subspace formed by known active molecules. From a Bayesian point of view, distance calculations are transformed into a "log-odds" estimate. Following this approach, maximizing the likelihood of a compound to be active corresponds to minimizing the distance from the center of an active subspace. Since the methodology generates a ranking of database molecules according to decreasing similarity to template compounds, it can be conveniently compared to similarity search tools, and the Bayesian function is found to compare favorably to two standard fingerprints in multiple template-based database searching.

## 16862. Cat-a-Cone

- 标题：Cat-a-Cone
- 作者：Marti A. Hearst, Chandu Karadi
- 年份：1997
- 出版日期：1997-07-01
- 类型：article
- 语言：en
- 来源：ACM SIGIR Forum
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：0163-5840
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/278459.258582
- OpenAlex ID：https://openalex.org/W3006664937
- 落地页：https://doi.org/10.1145/278459.258582
- 主主题：Information Retrieval and Search Behavior
- 主题：Information Retrieval and Search Behavior, Image Retrieval and Classification Techniques, Machine Learning and Algorithms
- 关键词：Citation, Computer science, Library science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
article Cat-a-Cone: an interactive interface for specifying searches and viewing retrieval results using a large category hierarchy Share on Authors: Marti A. Hearst Xerox Palo Alto Research Center, 3333 Coyote Hill Rd, Palo Alto, CA Xerox Palo Alto Research Center, 3333 Coyote Hill Rd, Palo Alto, CAView Profile , Chandu Karadi School of Medicine, M121, Stanford University, Stanford, CA School of Medicine, M121, Stanford University, Stanford, CAView Profile Authors Info & Claims ACM SIGIR ForumVolume 31Issue SIDecember 1997 pp 246–255https://doi.org/10.1145/278459.258582Published:01 July 1997 98citation1,350DownloadsMetricsTotal Citations98Total Downloads1,350Last 12 Months19Last 6 weeks2 Get Citation AlertsNew Citation Alert added!This alert has been successfully added and will be sent to:You will be notified whenever a record that you have chosen has been cited.To manage your alert preferences, click on the button below.Manage my AlertsNew Citation Alert!Please log in to your account Save to BinderSave to BinderCreate a New BinderNameCancelCreateExport CitationPublisher SiteGet Access

## 16863. Multiclass Classification with Multi-Prototype Support Vector Machines

- 标题：Multiclass Classification with Multi-Prototype Support Vector Machines
- 作者：AiolliFabio, SperdutiAlessandro
- 年份：2005
- 出版日期：2005-12-01
- 类型：article
- 语言：en
- 来源：Journal of Machine Learning Research
- 来源类型：journal
- 出版方：The MIT Press
- ISSN-L：1532-4435
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.5555/1046920.1088700
- OpenAlex ID：https://openalex.org/W3162561077
- 落地页：https://dl.acm.org/doi/10.5555/1046920.1088700
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Machine Learning and Data Classification, Face and Expression Recognition
- 关键词：Multiclass classification, Artificial intelligence, Support vector machine, Computer science, Machine learning, Set (abstract data type), Structured support vector machine, Class (philosophy), Pattern recognition (psychology), Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Winner-take-all multiclass classifiers are built on the top of a set of prototypes each representing one of the available classes. A pattern is then classified with the label associated to the most...

## 16864. Guessing Secrets

- 标题：Guessing Secrets
- 作者：Fan Chung, Ronald Graham, Tom Leighton
- 年份：2001
- 出版日期：2001-02-15
- 类型：article
- 语言：en
- 来源：The Electronic Journal of Combinatorics
- 来源类型：journal
- 出版方：Electronic Journal of Combinatorics
- ISSN-L：1077-8926
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.37236/1557
- OpenAlex ID：https://openalex.org/W4234960572
- 落地页：https://doi.org/10.37236/1557
- 开放 PDF 链接：https://www.combinatorics.org/ojs/index.php/eljc/article/download/v8i1r13/pdf
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, Complexity and Algorithms in Graphs
- 关键词：Omega, Mathematics, Combinatorics, Object (grammar), Set (abstract data type), Function (biology), Binary number, Value (mathematics), Discrete mathematics, Adversary, Upper and lower bounds, Arithmetic, Computer science, Artificial intelligence, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Suppose we are given some fixed (but unknown) subset $X$ of a set $\Omega$, and our object is to learn as much as possible about the elements of $X$ by asking binary questions. Specifically, each question is just a function $F: \Omega \rightarrow \{0,1\}$, and the answer to $F$ is just the value $F(X_i)$ for some $X_i \in X$, (determined, for example, by a potentially malevolent but truthful, adversary). In this paper, we describe various algorithms for solving this problem, and establish upper and lower bounds on the efficiency of such algorithms.

## 16865. Sampling with Unequal Probabilities.

- 标题：Sampling with Unequal Probabilities.
- 作者：M. E. Thompson, K. R. W. Brewer, Muhammad Hanif
- 年份：1984
- 出版日期：1984-06-01
- 类型：article
- 语言：en
- 来源：Journal of the American Statistical Association
- 来源类型：journal
- ISSN-L：0162-1459
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.2307/2288312
- OpenAlex ID：https://openalex.org/W4301232792
- 落地页：https://doi.org/10.2307/2288312
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms
- 关键词：Statistics, Sampling (signal processing), Mathematics, Computer science, Environmental science, Econometrics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16866. Coupled Samples in Simulation

- 标题：Coupled Samples in Simulation
- 作者：Luc Devroye
- 年份：1990
- 出版日期：1990-02-01
- 类型：article
- 语言：en
- 来源：Operations Research
- 来源类型：journal
- 出版方：Institute for Operations Research and the Management Sciences
- ISSN-L：0030-364X
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1287/opre.38.1.115
- OpenAlex ID：https://openalex.org/W1963687814
- 落地页：https://doi.org/10.1287/opre.38.1.115
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, Simulation Techniques and Applications
- 关键词：Independent and identically distributed random variables, Sequence (biology), Coupling (piping), Property (philosophy), Combinatorics, Mathematics, Computer science, Random variable, Physics, Statistical physics, Statistics, Materials science, Chemistry
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Assume that we wish to generate two samples of n independent identically distributed random variables, (X 1 ,…, X n ) and (Y 1 ,…, Y n ), where X 1 and Y 1 have densities f and g, respectively. If these samples are used in a simulation, and f is close to g, it is sometimes desirable to have close simulation results. This can be achieved by insisting that both samples agree in most of their components, that is, X i =Y i for as many i as possible under the given distributional constraints. Samples with this property are said to be optimally coupled. In this paper, we propose and study various methods of coupling two samples, a sequence of samples and an infinite family of samples.

## 16867. Comparing Bayesian neural network algorithms for classifying segmented outdoor images

- 标题：Comparing Bayesian neural network algorithms for classifying segmented outdoor images
- 作者：Francesco Vivarelli, Christopher K. I. Williams
- 年份：2001
- 出版日期：2001-05-01
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/s0893-6080(01)00024-7
- OpenAlex ID：https://openalex.org/W1974545290
- 落地页：https://doi.org/10.1016/s0893-6080(01)00024-7
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Machine Learning and Data Classification, Anomaly Detection Techniques and Applications
- 关键词：Artificial neural network, Computer science, Artificial intelligence, Bayesian probability, Markov chain Monte Carlo, Machine learning, Pattern recognition (psychology), Feature (linguistics), Relevance (law), Image (mathematics), Bayesian network, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16868. Learning Recursive Functions from Approximations

- 标题：Learning Recursive Functions from Approximations
- 作者：John Case, Susanne Kaufmann, Efim Kinber, Martin Kummer
- 年份：1997
- 出版日期：1997-08-01
- 类型：article
- 语言：en
- 来源：Journal of Computer and System Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0022-0000
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1006/jcss.1997.1508
- OpenAlex ID：https://openalex.org/W1980411366
- 落地页：https://doi.org/10.1006/jcss.1997.1508
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, Machine Learning and Data Classification
- 关键词：Approximations of π, Recursive functions, Mathematics, Computer science, Mathematical optimization, Discrete mathematics, Applied mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16869. Search in an Ordered Array Having Variable Probe Cost

- 标题：Search in an Ordered Array Having Variable Probe Cost
- 作者：William J. Knight
- 年份：1988
- 出版日期：1988-12-01
- 类型：article
- 语言：en
- 来源：SIAM Journal on Computing
- 来源类型：journal
- 出版方：Society for Industrial and Applied Mathematics
- ISSN-L：0097-5397
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1137/0217076
- OpenAlex ID：https://openalex.org/W1983477045
- 落地页：https://doi.org/10.1137/0217076
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Optimization and Search Problems, Algorithms and Data Compression
- 关键词：Filter (signal processing), Combinatorics, Binary search algorithm, Integer (computer science), Binary number, Algorithm, Mathematics, Computer science, Search algorithm, Arithmetic
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Steiglitz and Parks [“What Is the Filter-Design Problem?,” Proc. 1986 Princeton Conference on Information Science and Systems, B. W. Dickenson, ed., Princeton University, Dept. of Electrical Engineering, Princeton, NJ, 1986] have shown that a problem in filter design gives rise to a related problem of how to search an ordered array in which the cost of a probe into the array varies with the location being probed. In this paper we prove that if probing in location k has cost $k^p $, where p is a positive integer, then the expected cost of a successful or unsuccessful search for a target element is at least $(p + 1)^{ - 1} n^p \lg n + O(n^p )$. We also prove the somewhat surprising fact that ordinary binary search has this expected cost. However, for the case $p = 1$ we describe what appears to be a marginally better search algorithm.

## 16870. Inductive inference from theory laden data

- 标题：Inductive inference from theory laden data
- 作者：KevinT. Kelly, Clark Glymour
- 年份：1992
- 出版日期：1992-11-01
- 类型：article
- 语言：en
- 来源：Journal of Philosophical Logic
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0022-3611
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/bf00260743
- OpenAlex ID：https://openalex.org/W1995163355
- 落地页：https://doi.org/10.1007/bf00260743
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Machine Learning and Data Classification, Algorithms and Data Compression
- 关键词：Inference, Inductive reasoning, Epistemology, Computer science, Philosophy
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16871. Fast Nearest Neighbor Classification Methods for Multispectral Imagery

- 标题：Fast Nearest Neighbor Classification Methods for Multispectral Imagery
- 作者：Perry J. Hardin, Curtis N. Thomson
- 年份：1992
- 出版日期：1992-05-01
- 类型：article
- 语言：en
- 来源：The Professional Geographer
- 来源类型：journal
- 出版方：Routledge
- ISSN-L：0033-0124
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1111/j.0033-0124.1992.00191.x
- OpenAlex ID：https://openalex.org/W2002738688
- 落地页：https://doi.org/10.1111/j.0033-0124.1992.00191.x
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Face and Expression Recognition, Advanced Image and Video Retrieval Techniques
- 关键词：k-nearest neighbors algorithm, Computer science, Best bin first, Multispectral image, Pattern recognition (psychology), Artificial intelligence, Nearest-neighbor chain algorithm, Nearest neighbor search, Decision tree, Large margin nearest neighbor, Cover tree, Pixel, Data mining, Cluster analysis
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Nearest neighbor classifiers have not been widely used by remote sensing practitioners. The lack of acceptance of these classifiers may be partially due to their notoriously slow speed of execution which makes them impractical for the classification of mega-pixel images. However, training data reduction, distance measure optimization, and neighbor searching algorithms based on the modified k-d tree can speed nearest neighbor classification substantially.

## 16872. The Problem of Estimation.

- 标题：The Problem of Estimation.
- 作者：A. J. Beamish, Correa Moylan Walsh
- 年份：1922
- 出版日期：1922-06-01
- 类型：article
- 语言：en
- 来源：The Economic Journal
- 来源类型：journal
- 出版方：Oxford University Press
- ISSN-L：0013-0133
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.2307/2223262
- OpenAlex ID：https://openalex.org/W2017679124
- 落地页：https://doi.org/10.2307/2223262
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Computability, Logic, AI Algorithms, Statistics Education and Methodologies
- 关键词：Estimation, Economics, Econometrics, Management
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16873. Modeling user context with applications to media retrieval

- 标题：Modeling user context with applications to media retrieval
- 作者：Ankur Mani, Hari Sundaram
- 年份：2006
- 出版日期：2006-08-29
- 类型：article
- 语言：en
- 来源：Multimedia Systems
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0942-4962
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00530-006-0054-9
- OpenAlex ID：https://openalex.org/W2030285002
- 落地页：https://doi.org/10.1007/s00530-006-0054-9
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Image Retrieval and Classification Techniques, Multimodal Machine Learning Applications
- 关键词：Computer science, Representation (politics), Context (archaeology), Key (lock), Knowledge representation and reasoning, Set (abstract data type), Human–computer interaction, Information retrieval, Data science, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16874. Criteria for Polynomial-Time (Conceptual) Clustering

- 标题：Criteria for Polynomial-Time (Conceptual) Clustering
- 作者：Leonard Pitt, Robert E. Reinke
- 年份：1988
- 出版日期：1988-04-01
- 类型：article
- 语言：en
- 来源：Machine Learning
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-6125
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1023/a:1022825229661
- OpenAlex ID：https://openalex.org/W2033361580
- 落地页：https://doi.org/10.1023/a:1022825229661
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1023/A:1022825229661.pdf
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Optimization and Search Problems, Algorithms and Data Compression
- 关键词：Computer science, Artificial intelligence, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16875. Logical analysis of Chinese labor productivity patterns

- 标题：Logical analysis of Chinese labor productivity patterns
- 作者：Alexander B. Hammer, P. L. Hammer, Ilya Muchnik
- 年份：1999
- 出版日期：1999-04-01
- 类型：article
- 语言：en
- 来源：Annals of Operations Research
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0254-5330
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1023/a:1018920600320
- OpenAlex ID：https://openalex.org/W2038863657
- 落地页：https://doi.org/10.1023/a:1018920600320
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Mineral Processing and Grinding, Machine Learning and Data Classification
- 关键词：Theory of computation, Computer science, Mathematical economics, Mathematics, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16876. Overlap-free words and finite automata

- 标题：Overlap-free words and finite automata
- 作者：Arturo Carpi
- 年份：1993
- 出版日期：1993-07-01
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/0304-3975(93)90118-d
- OpenAlex ID：https://openalex.org/W2050063865
- 落地页：https://doi.org/10.1016/0304-3975(93)90118-d
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, DNA and Biological Computing, Machine Learning and Algorithms
- 关键词：Alphabet, Word (group theory), Binary number, Set (abstract data type), Function (biology), Automaton, Combinatorics on words, Mathematics, Regular language, Combinatorics, Computer science, Discrete mathematics, Theoretical computer science, Arithmetic, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16877. Learning Horn definitions: Theory and an application to planning

- 标题：Learning Horn definitions: Theory and an application to planning
- 作者：Chandra Reddy, Prasad Tadepalli
- 年份：1999
- 出版日期：1999-03-01
- 类型：article
- 语言：en
- 来源：New Generation Computing
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0288-3635
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/bf03037583
- OpenAlex ID：https://openalex.org/W2054073879
- 落地页：https://doi.org/10.1007/bf03037583
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, AI-based Problem Solving and Planning, Logic, Reasoning, and Knowledge
- 关键词：Computer science, Horn clause, French horn, Predicate (mathematical logic), Logical consequence, Class (philosophy), Logic program, First-order logic, Equivalence (formal languages), Artificial intelligence, Theoretical computer science, Prolog, Logic programming, Programming language, Discrete mathematics, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16878. An Error Correcting Procedure for Learning with an Imperfect Teacher

- 标题：An Error Correcting Procedure for Learning with an Imperfect Teacher
- 作者：K. Shanmugam, A.M. Breipohl
- 年份：1971
- 出版日期：1971-07-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Systems Man and Cybernetics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9472
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tsmc.1971.4308289
- OpenAlex ID：https://openalex.org/W2057256083
- 落地页：https://doi.org/10.1109/tsmc.1971.4308289
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Machine Learning and Algorithms, Machine Learning and Data Classification
- 关键词：Scheme (mathematics), Imperfect, Computer science, Error detection and correction, Set (abstract data type), Artificial intelligence, Generalization error, Probably approximately correct learning, Sample (material), Machine learning, Simple (philosophy), Algorithm, Pattern recognition (psychology), Mathematics, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Supervised learning in pattern recognition problems takes place through the use of a set of labeled sample patterns, the labels being provided by a "teacher." In most of the procedures for learning with a teacher, it is commonly assumed that the teacher is perfect, i. e., the labels of the sample patterns are always correct. However, there are many circumstances in which the patterns used for learning are occasionally mislabeled. A procedure for learning with an imperfect teacher who occasionally mislabels some of the learning patterns is developed. The proposed error correction scheme is based on a nonparametric learning scheme. The error correction scheme questions and attempts to correct the labels provided by the imperfect teacher using a threshold in the correction scheme. The use of threshold facilitates control over the amount of correction and provides a simple method for combining the knowledge acquired by the learning scheme with that provided by the teacher. Expressions for the threshold are derived, and the properties of the proposed error correction scheme are discussed. Through computer simulations the performance of the proposed error correction scheme is compared with that of an identical learning scheme without error correction.

## 16879. Representations of semigroups by linear transformations

- 标题：Representations of semigroups by linear transformations
- 作者：Donald B. McAlister
- 年份：1971
- 出版日期：1971-01-01
- 类型：article
- 语言：en
- 来源：Semigroup Forum
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0037-1912
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/bf02572292
- OpenAlex ID：https://openalex.org/W2058593413
- 落地页：https://doi.org/10.1007/bf02572292
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Logic, programming, and type systems, Machine Learning and Algorithms
- 关键词：Mathematics, Algebra over a field, Pure mathematics, Inverse semigroup, Arithmetic
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16880. Causality‐based failure‐driven learning in diagnostic expert systems

- 标题：Causality‐based failure‐driven learning in diagnostic expert systems
- 作者：Steven H. Rich, Venkat Venkatasubramanian
- 年份：1989
- 出版日期：1989-06-01
- 类型：article
- 语言：en
- 来源：AIChE Journal
- 来源类型：journal
- 出版方：Wiley
- ISSN-L：0001-1541
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1002/aic.690350607
- OpenAlex ID：https://openalex.org/W2060329716
- 落地页：https://doi.org/10.1002/aic.690350607
- 主主题：AI-based Problem Solving and Planning
- 主题：AI-based Problem Solving and Planning, Bayesian Modeling and Causal Inference, Machine Learning and Algorithms
- 关键词：Heuristics, Heuristic, Expert system, Computer science, Machine learning, Causality (physics), Artificial intelligence, Process (computing), State (computer science), Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract It has been recognized that a diagnostic expert system's ability to learn from past experience will improve its diagnostic efficiency as well as make it acquire new heuristics. In this paper, we propose a failure‐driven learning scheme by which the expert system automatically updates its compiled knowledge by acquiring new heuristics or refining existing heuristics. A heuristic is refined if it hypothesizes the wrong causal origin during a diagnosis. Using its deep‐level knowledge of the process, the expert system draws inductive inferences from causal models to determine why the hypothesis proposed by the heuristic is inconsistent with the current state of the process. The refinement limits the applicability of the heuristic and prevents it from firing if a similar situation were to subsequently arise.

## 16881. Strategies for cursive script recognition using hidden Markov models

- 标题：Strategies for cursive script recognition using hidden Markov models
- 作者：M. Gilloux, Manuel Leroux, J.-M. Bertille
- 年份：1995
- 出版日期：1995-07-01
- 类型：article
- 语言：en
- 来源：Machine Vision and Applications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0932-8092
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/bf01219587
- OpenAlex ID：https://openalex.org/W2066998833
- 落地页：https://doi.org/10.1007/bf01219587
- 主主题：Handwritten Text Recognition Techniques
- 主题：Handwritten Text Recognition Techniques, Machine Learning and Algorithms, Natural Language Processing Techniques
- 关键词：Hidden Markov model, Computer science, Vocabulary, Cursive, Natural language processing, Artificial intelligence, Word (group theory), Lexicon, Word recognition, Representation (politics), Speech recognition, Markov chain, Linguistics, Machine learning, Reading (process)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16882. On the application of formal language and automata theory to pattern recognition

- 标题：On the application of formal language and automata theory to pattern recognition
- 作者：John Mylopoulos
- 年份：1972
- 出版日期：1972-01-01
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/0031-3203(72)90018-0
- OpenAlex ID：https://openalex.org/W2078730851
- 落地页：https://doi.org/10.1016/0031-3203(72)90018-0
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Machine Learning and Algorithms, DNA and Biological Computing
- 关键词：Automaton, Quantum finite automata, Automata theory, Class (philosophy), Computer science, ω-automaton, Continuous spatial automaton, Nested word, Theoretical computer science, Set (abstract data type), Mobile automaton, Pushdown automaton, Algorithm, Finite-state machine, Mathematics, Discrete mathematics, Artificial intelligence, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16883. Automata and languages generalized to ω-continuous semirings

- 标题：Automata and languages generalized to ω-continuous semirings
- 作者：Werner Kuich
- 年份：1991
- 出版日期：1991-02-01
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/0304-3975(91)90147-t
- OpenAlex ID：https://openalex.org/W2079940288
- 落地页：https://doi.org/10.1016/0304-3975(91)90147-t
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Machine Learning and Algorithms, Advanced Algebra and Logic
- 关键词：Abstract family of languages, Nested word, Automaton, Regular language, Mathematics, Discrete mathematics, Pushdown automaton, Finite-state machine, Class (philosophy), Automata theory, Computer science, Quantum finite automata, Programming language, Theoretical computer science, Algorithm, Second-generation programming language, Artificial intelligence, Fifth-generation programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16884. Convexity and logical analysis of data

- 标题：Convexity and logical analysis of data
- 作者：Oya Ekin, Peter L. Hammer, Alexander Kogan
- 年份：2000
- 出版日期：2000-08-01
- 类型：article
- 语言：en
- 来源：Theoretical Computer Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0304-3975
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/s0304-3975(98)00337-5
- OpenAlex ID：https://openalex.org/W2095990137
- 落地页：https://doi.org/10.1016/s0304-3975(98)00337-5
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Complexity and Algorithms in Graphs, Machine Learning and Data Classification
- 关键词：Mathematics, Combinatorics, Boolean function, Discrete mathematics, Parity function, Convexity, Uniqueness, Convex set, Regular polygon, Convex analysis, Boolean expression, Convex optimization
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16885. Necessary and sufficient conditions for Bayes risk consistency of a recursive kernel classification rule (Corresp.)

- 标题：Necessary and sufficient conditions for Bayes risk consistency of a recursive kernel classification rule (Corresp.)
- 作者：Włodzimierz Greblicki, M. Pawlak
- 年份：1987
- 出版日期：1987-05-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tit.1987.1057309
- OpenAlex ID：https://openalex.org/W2103717848
- 落地页：https://doi.org/10.1109/tit.1987.1057309
- 主主题：Rough Sets and Fuzzy Logic
- 主题：Rough Sets and Fuzzy Logic, Bayesian Modeling and Causal Inference, Machine Learning and Algorithms
- 关键词：Consistency (knowledge bases), Bayes' theorem, Kernel (algebra), Combinatorics, Nonparametric statistics, Mathematics, Discrete mathematics, Algorithm, Artificial intelligence, Computer science, Statistics, Bayesian probability
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
It is shown that, for a nonparametric recursive kernel classification rule, <tex xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">\sum^{n}_{i=1}h^{d}(i)I_{ \{h(i) &gt; \epsilon \} } / \sum^{n}_{j=1} h^{d} (j) \rightarrow 0 {\rm as} n \rightarrow \infty,</tex> all <tex xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">\epsilon &gt; 0</tex> and <tex xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">\sum^{\infty}_{i=1}h^{d}(i)= \infty</tex> constitute a set of conditions which are not only sufficient but also necessary for weak and strong Bayes risk consistency of the rule. In this way, weak and strong consistencies are shown to be equivalent.

## 16886. The structure of intrinsic complexity of learning

- 标题：The structure of intrinsic complexity of learning
- 作者：Sanjay Jain, Arun Sharma
- 年份：1997
- 出版日期：1997-12-01
- 类型：article
- 语言：en
- 来源：Journal of Symbolic Logic
- 来源类型：journal
- 出版方：Cambridge University Press
- ISSN-L：0022-4812
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.2307/2275636
- OpenAlex ID：https://openalex.org/W2122008636
- 落地页：https://doi.org/10.2307/2275636
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Computability, Logic, AI Algorithms, semigroups and automata theory
- 关键词：Learnability, Computer science, Theoretical computer science, Directed acyclic graph, Recursion (computer science), Identification (biology), Mathematics, Artificial intelligence, Discrete mathematics, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Limiting identification of r.e. indexes for r.e. languages (from a presentation of elements of the language) and limiting identification of programs for computable functions (from a graph of the function) have served as models for investigating the boundaries of learnability. Recently, a new approach to the study of “intrinsic” complexity of identification in the limit has been proposed. This approach, instead of dealing with the resource requirements of the learning algorithm, uses the notion of reducibility from recursion theory to compare and to capture the intuitive difficulty of learning various classes of concepts. Freivalds, Kinber, and Smith have studied this approach for function identification and Jain and Sharma have studied it for language identification. The present paper explores the structure of these reducibilities in the context of language identification. It is shown that there is an infinite hierarchy of language classes that represent learning problems of increasing difficulty. It is also shown that the language classes in this hierarchy are incomparable, under the reductions introduced, to the collection of pattern languages. Richness of the structure of intrinsic complexity is demonstrated by proving that any finite, acyclic, directed graph can be embedded in the reducibility structure. However, it is also established that this structure is not dense. The question of embedding any infinite, acyclic, directed graph is open.

## 16887. Some properties of sequential predictors for binary Markov sources

- 标题：Some properties of sequential predictors for binary Markov sources
- 作者：Neri Merhav, Meir Feder, M. Gutman
- 年份：1993
- 出版日期：1993-05-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/18.256496
- OpenAlex ID：https://openalex.org/W2125889002
- 落地页：https://doi.org/10.1109/18.256496
- 主主题：Algorithms and Data Compression
- 主题：Algorithms and Data Compression, Machine Learning and Algorithms, DNA and Biological Computing
- 关键词：Predictability, Bernoulli's principle, Upper and lower bounds, Markov chain, Binary number, Pseudorandom binary sequence, Mathematics, Fraction (chemistry), Markov process, Markov model, Variable-order Markov model, Statistics, Bernoulli trial, Discrete mathematics, Sequence (biology), Combinatorics, Algorithm, Computer science, Applied mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Universal predictions of the next outcome of a binary sequence drawn from a Markov source with unknown parameters is considered. For a given source, the predictability is defined as the least attainable expected fraction of prediction errors. A lower bound is derived on the maximum rate at which the predictability is asymptotically approached uniformly over all sources in the Markov class. This bound is achieved by a simple majority predictor. For Bernoulli sources, bounds on the large deviations performance are investigated. A lower bound is derived for the probability that the fraction of errors will exceed the predictability by a prescribed amount Delta >0. This bound is achieved by the same predictor if Delta is sufficiently small.< <ETX xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">&gt;</ETX>

## 16888. Finding the k Shortest Paths in Parallel

- 标题：Finding the k Shortest Paths in Parallel
- 作者：Eric Ruppert
- 年份：2000
- 出版日期：2000-10-01
- 类型：article
- 语言：en
- 来源：Algorithmica
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0178-4617
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s004530010038
- OpenAlex ID：https://openalex.org/W2135819212
- 落地页：https://doi.org/10.1007/s004530010038
- 主主题：Complexity and Algorithms in Graphs
- 主题：Complexity and Algorithms in Graphs, Machine Learning and Algorithms, Advanced Graph Theory Research
- 关键词：Combinatorics, Binary logarithm, Mathematics, Vertex (graph theory), Shortest path problem, Log-log plot, Distance, Graph, Theory of computation, Discrete mathematics, Algorithm
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16889. On learning context-free and context-sensitive languages

- 标题：On learning context-free and context-sensitive languages
- 作者：Mikael Bodén, Janet Wiles
- 年份：2002
- 出版日期：2002-03-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1045-9227
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1109/72.991436
- OpenAlex ID：https://openalex.org/W2161658801
- 落地页：https://doi.org/10.1109/72.991436
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Machine Learning and Algorithms, Neural Networks and Reservoir Computing
- 关键词：Computer science, Context (archaeology), Set (abstract data type), Artificial intelligence, Artificial neural network, Context-dependent memory, Natural language processing, Context model, Recurrent neural network, Machine learning, Theoretical computer science, Programming language, Cognitive psychology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The long short-term memory (LSTM) is not the only neural network which learns a context sensitive language. Second-order sequential cascaded networks (SCNs) are able to induce means from a finite fragment of a context-sensitive language for processing strings outside the training set. The dynamical behavior of the SCN is qualitatively distinct from that observed in LSTM networks. Differences in performance and dynamics are discussed.

## 16890. Cost-conscious classifier ensembles

- 标题：Cost-conscious classifier ensembles
- 作者：Cigdem Demir, Ethem Alpaydın
- 年份：2005
- 出版日期：2005-05-24
- 类型：article
- 语言：en
- 来源：Pattern Recognition Letters
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0167-8655
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patrec.2005.03.028
- OpenAlex ID：https://openalex.org/W2162479195
- 落地页：https://doi.org/10.1016/j.patrec.2005.03.028
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Anomaly Detection Techniques and Applications, Data Stream Mining Techniques
- 关键词：Classifier (UML), Computer science, Artificial intelligence, Random subspace method, Machine learning, Cascading classifiers, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16891. Optimal Biweighted Binary Trees and the Complexity of Maintaining Partial Sums

- 标题：Optimal Biweighted Binary Trees and the Complexity of Maintaining Partial Sums
- 作者：Haripriyan Hampapuram, Michael L. Fredman
- 年份：1998
- 出版日期：1998-01-01
- 类型：article
- 语言：en
- 来源：SIAM Journal on Computing
- 来源类型：journal
- 出版方：Society for Industrial and Applied Mathematics
- ISSN-L：0097-5397
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1137/s0097539795291598
- OpenAlex ID：https://openalex.org/W2162481025
- 落地页：https://doi.org/10.1137/s0097539795291598
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Complexity and Algorithms in Graphs, Advanced Graph Theory Research
- 关键词：Mathematics, Binary tree, Weighting, Binary number, Combinatorics, Discrete mathematics, Computation, Tree (set theory), Upper and lower bounds, Binary search tree, Semigroup, Type (biology), Subset sum problem, Algorithm, Arithmetic
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Let A be an array. The partial sum problem concerns the design of a data structure for implementing the following operations. The operation update (j,x) has the effect $A[j] \leftarrow A[j]+x \,$, and the query operation $\ssum(j)$ returns the partial sum $\sum_{i=1}^j \, A[i] \,$. Our interest centers upon the optimal efficiency with which sequences of such operations can be performed, and we derive new upper and lower bounds in the semigroup model of computation. Our analysis relates the optimal complexity of the partial sum problem to optimal binary trees relative to a type of weighting scheme that defines the notion of biweighted binary tree.

## 16892. Randomised allocation of treatments in sequential trials

- 标题：Randomised allocation of treatments in sequential trials
- 作者：J. A. Bather
- 年份：1980
- 出版日期：1980-03-01
- 类型：article
- 语言：en
- 来源：Advances in Applied Probability
- 来源类型：journal
- 出版方：Cambridge University Press
- ISSN-L：0001-8678
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.2307/1426500
- OpenAlex ID：https://openalex.org/W2323057311
- 落地页：https://doi.org/10.2307/1426500
- 主主题：Advanced Bandit Algorithms Research
- 主题：Advanced Bandit Algorithms Research, Auction Theory and Applications, Machine Learning and Algorithms
- 关键词：Mathematics, Sequence (biology), Class (philosophy), Property (philosophy), Mathematical optimization, Combinatorics, Statistics, Artificial intelligence, Computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Given a finite number of different experiments with unknown probabilities p 1 , p 2 , ···, p k of success, the multi-armed bandit problem is concerned with maximising the expected number of successes in a sequence of trials. There are many policies which ensure that the proportion of successes converges to p = max ( p 1 , p 2 , ···, p k ), in the long run. This property is established for a class of decision procedures which rely on randomisation, at each stage, in selecting the experiment for the next trial. Further, it is suggested that some of these procedures might perform well over any finite sequence of trials.

## 16893. Regression Diagnostics with Dynamic Graphics: [With Discussions and Response]

- 标题：Regression Diagnostics with Dynamic Graphics: [With Discussions and Response]
- 作者：R. Dennis Cook, Sanford Weisberg, Daniel B. Carr, Daryl Pregibon, Anthony C. Atkinson, Luke Tierney, Roy E. Welsch
- 年份：1989
- 出版日期：1989-08-01
- 类型：article
- 语言：en
- 来源：Technometrics
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0040-1706
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.2307/3556140
- OpenAlex ID：https://openalex.org/W2328202351
- 落地页：https://doi.org/10.2307/3556140
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Machine Learning and Data Classification
- 关键词：Graphics, Computer science, Regression, Computer graphics (images), Mathematics, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
R. Dennis Cook, Sanford Weisberg, Daniel B. Carr, Daryl Pregibon, A. C. Atkinson, Luke Tierney, Roy E. Welsch, Regression Diagnostics with Dynamic Graphics: [With Discussions and Response], Technometrics, Vol. 31, No. 3 (Aug., 1989), pp. 277-291+293-301+303-311

## 16894. The candidate problem with unknown population size

- 标题：The candidate problem with unknown population size
- 作者：W. T. Rasmussen, Herbert Robbins
- 年份：1975
- 出版日期：1975-12-01
- 类型：article
- 语言：en
- 来源：Journal of Applied Probability
- 来源类型：journal
- 出版方：Cambridge University Press
- ISSN-L：0021-9002
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1017/s0021900200048658
- OpenAlex ID：https://openalex.org/W2328683679
- 落地页：https://doi.org/10.1017/s0021900200048658
- 主主题：Optimization and Search Problems
- 主题：Optimization and Search Problems, Machine Learning and Algorithms, Random Matrices and Applications
- 关键词：Mathematics, Combinatorics, A priori and a posteriori, Probability distribution, Group (periodic table), Distribution (mathematics), Population, Statistics, Discrete mathematics, Mathematical analysis, Demography
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The familiar problem of maximizing the probability of choosing the best from a group of N candidates, where N is known, is extended to the case of N unknown. An a priori distribution is assumed for N, and the case of a uniform distribution is examined. Let V N denote the probability of choosing the best from a group of at most N candidates, then it is shown that lim N →∞ V N = 2 e –2 .

## 16895. Using neural networks to modularize software

- 标题：Using neural networks to modularize software
- 作者：Robert W. Schwanke, Stephen Jos� Hanson
- 年份：1994
- 出版日期：1994-05-01
- 类型：article
- 语言：en
- 来源：Machine Learning
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-6125
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1007/bf00993275
- OpenAlex ID：https://openalex.org/W4236646925
- 落地页：https://doi.org/10.1007/bf00993275
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/BF00993275.pdf
- 主主题：Software Engineering Research
- 主题：Software Engineering Research, Machine Learning and Data Classification, Data Stream Mining Techniques
- 关键词：Computer science, Modular programming, Artificial intelligence, Classifier (UML), Modularity (biology), Artificial neural network, Machine learning, Cluster analysis, Generalization, Software, Field (mathematics), Architecture, Data mining, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16896. Computing Optimal Attribute Weight Settings for Nearest Neighbor Algorithms

- 标题：Computing Optimal Attribute Weight Settings for Nearest Neighbor Algorithms
- 作者：Charles X. Ling, Hangdong Wang
- 年份：1997
- 出版日期：1997-02-01
- 类型：article
- 语言：en
- 来源：Artificial Intelligence Review
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0269-2821
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1023/a:1006560730186
- OpenAlex ID：https://openalex.org/W2013148653
- 落地页：https://doi.org/10.1023/a:1006560730186
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Machine Learning and Algorithms, Imbalanced Data Classification Techniques
- 关键词：Discriminative model, Computer science, Artificial intelligence, Measure (data warehouse), Similarity (geometry), Function (biology), Machine learning, Algorithm, Pattern recognition (psychology), Mathematics, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16897. A simple algorithm for learning O(log n)-term DNF

- 标题：A simple algorithm for learning O(log n)-term DNF
- 作者：Eyal Kushilevitz
- 年份：1997
- 出版日期：1997-03-01
- 类型：article
- 语言：en
- 来源：Information Processing Letters
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0190
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/s0020-0190(97)00026-4
- OpenAlex ID：https://openalex.org/W2052679199
- 落地页：https://doi.org/10.1016/s0020-0190(97)00026-4
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, semigroups and automata theory
- 关键词：Term (time), Simple (philosophy), Computer science, Algorithm, Mathematics, Combinatorics, Artificial intelligence, Physics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16898. Polynomial time learnability of simple deterministic languages

- 标题：Polynomial time learnability of simple deterministic languages
- 作者：Hiroki Ishizaka
- 年份：1990
- 出版日期：1990-06-01
- 类型：article
- 语言：en
- 来源：Machine Learning
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-6125
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1007/bf00116035
- OpenAlex ID：https://openalex.org/W4256717243
- 落地页：https://doi.org/10.1007/bf00116035
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/BF00116035.pdf
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, semigroups and automata theory
- 关键词：Terminal and nonterminal symbols, Grammar induction, Learnability, Equivalence (formal languages), Simple (philosophy), Mathematics, Time complexity, Counterexample, Discrete mathematics, Grammar, Computer science, Rule-based machine translation, Algorithm, Theoretical computer science, Artificial intelligence, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16899. Testing and Spot-Checking of Data Streams

- 标题：Testing and Spot-Checking of Data Streams
- 作者：Feigenbaum, K. Kannan, Strauss, V. Viswanathan
- 年份：2002
- 出版日期：2002-09-01
- 类型：article
- 语言：en
- 来源：Algorithmica
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0178-4617
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s00453-002-0959-4
- OpenAlex ID：https://openalex.org/W1558846832
- 落地页：https://doi.org/10.1007/s00453-002-0959-4
- 主主题：Complexity and Algorithms in Graphs
- 主题：Complexity and Algorithms in Graphs, Machine Learning and Algorithms, Optimization and Search Problems
- 关键词：Property (philosophy), Computer science, Data stream mining, STREAMS, Permutation (music), Context (archaeology), Data stream, Sampling (signal processing), Theory of computation, Real-time computing, Algorithm, Data mining, Detector
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16900. Inference of tree automata from sample set of trees

- 标题：Inference of tree automata from sample set of trees
- 作者：Hiroshi Fukuda, Ken Kamata
- 年份：1984
- 出版日期：1984-06-01
- 类型：article
- 语言：en
- 来源：International Journal of Parallel Programming
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-7458
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/bf00979871
- OpenAlex ID：https://openalex.org/W1975542793
- 落地页：https://doi.org/10.1007/bf00979871
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, semigroups and automata theory
- 关键词：Tree (set theory), Automaton, Sample (material), Set (abstract data type), Computer science, Inference, Tree automaton, K-ary tree, Tree structure, Mathematics, Algorithm, Theoretical computer science, Artificial intelligence, Combinatorics, Binary tree, Physics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16901. Unbounded Searching Algorithms

- 标题：Unbounded Searching Algorithms
- 作者：Richard Beigel
- 年份：1990
- 出版日期：1990-06-01
- 类型：article
- 语言：en
- 来源：SIAM Journal on Computing
- 来源类型：journal
- 出版方：Society for Industrial and Applied Mathematics
- ISSN-L：0097-5397
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1137/0219035
- OpenAlex ID：https://openalex.org/W1988287732
- 落地页：https://doi.org/10.1137/0219035
- 主主题：Algorithms and Data Compression
- 主题：Algorithms and Data Compression, Machine Learning and Algorithms, Optimization and Search Problems
- 关键词：Mathematics, Key (lock), Combinatorics, Upper and lower bounds, Algorithm, Search problem, Table (database), Discrete mathematics, Computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The unbounded search problem was posed by Bentley and Yao. It is the problem of finding a key in a linearly ordered unbounded table, with the proviso that the number of comparisons is to be minimized. It is shown that Bentley and Yao’s lower bound is essentially optimal, and some new upper bounds for the unbounded search problem are proven. The solution of this problem in parallel is demon-strated.

## 16902. On competitive on-line algorithms for the dynamic priority-ordering problem

- 标题：On competitive on-line algorithms for the dynamic priority-ordering problem
- 作者：G. Ramalingam, Thomas Reps
- 年份：1994
- 出版日期：1994-08-01
- 类型：article
- 语言：en
- 来源：Information Processing Letters
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0190
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/0020-0190(94)00080-8
- OpenAlex ID：https://openalex.org/W1988846076
- 落地页：https://doi.org/10.1016/0020-0190(94)00080-8
- 主主题：Optimization and Search Problems
- 主题：Optimization and Search Problems, Complexity and Algorithms in Graphs, Machine Learning and Algorithms
- 关键词：Computer science, Algorithm, Line (geometry), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16903. Amalgamation and inverse and regular semigroups

- 标题：Amalgamation and inverse and regular semigroups
- 作者：T. E. Hall
- 年份：1978
- 出版日期：1978-01-01
- 类型：article
- 语言：en
- 来源：Transactions of the American Mathematical Society
- 来源类型：journal
- 出版方：American Mathematical Society
- ISSN-L：0002-9947
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1090/s0002-9947-1978-0515546-8
- OpenAlex ID：https://openalex.org/W2006442046
- 落地页：https://doi.org/10.1090/s0002-9947-1978-0515546-8
- 开放 PDF 链接：https://www.ams.org/tran/1978-246-00/S0002-9947-1978-0515546-8/S0002-9947-1978-0515546-8.pdf
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Natural Language Processing Techniques, Machine Learning and Algorithms
- 关键词：Mathematics, Inverse semigroup, Inverse, Semigroup, Embedding, Special classes of semigroups, Inverse element, Pure mathematics, Cancellative semigroup, Bicyclic semigroup, Regular semigroup, Amalgam (chemistry), Algebra over a field, Discrete mathematics, Geometry, Computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A method for proving the embeddability of semigroup amalgams is introduced. After providing necessary and sufficient conditions in terms of representations for the weak embeddability of a semigroup amalgam, it successfully deals with the embedding of inverse semigroup amalgams into inverse semigroups and the embedding of an amalgam of regular semigroups whose core is full in each member.

## 16904. MEGA---the maximizing expected generalization algorithm for learning complex query concepts

- 标题：MEGA---the maximizing expected generalization algorithm for learning complex query concepts
- 作者：Edward Yi Chang, Beitao Li
- 年份：2003
- 出版日期：2003-10-01
- 类型：article
- 语言：en
- 来源：ACM Transactions on Information Systems
- 来源类型：journal
- ISSN-L：1046-8188
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/944012.944014
- OpenAlex ID：https://openalex.org/W2022743991
- 落地页：https://doi.org/10.1145/944012.944014
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Machine Learning and Algorithms, Image Retrieval and Classification Techniques
- 关键词：Computer science, Query optimization, Generalization, Task (project management), Query expansion, Process (computing), Speedup, Web search query, Query language, Web query classification, Object (grammar), Sargable, Data mining, Information retrieval, Machine learning, Artificial intelligence, Theoretical computer science, Search engine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Specifying exact query concepts has become increasingly challenging to end-users. This is because many query concepts (e.g., those for looking up a multimedia object) can be hard to articulate, and articulation can be subjective. In this study, we propose a query-concept learner that learns query criteria through an intelligent sampling process. Our concept learner aims to fulfill two primary design objectives: (1) it has to be expressive in order to model most practical query concepts and (2) it must learn a concept quickly and with a small number of labeled data since online users tend to be too impatient to provide much feedback. To fulfill the first goal, we model query concepts in k -CNF, which can express almost all practical query concepts. To fulfill the second design goal, we propose our maximizing expected generalization algorithm (MEGA), which converges to target concepts quickly by its two complementary steps: sample selection and concept refinement. We also propose a divide-and-conquer method that divides the concept-learning task into G subtasks to achieve speedup. We notice that a task must be divided carefully, or search accuracy may suffer. Through analysis and mining results, we observe that organizing image features in a multiresolution manner, and minimizing intragroup feature correlation, can speed up query-concept learning substantially while maintaining high search accuracy. Through examples, analysis, experiments, and a prototype implementation, we show that MEGA converges to query concepts significantly faster than traditional methods.

## 16905. On-Line Learning from Search Failures

- 标题：On-Line Learning from Search Failures
- 作者：Neeraj Bhatnagar, Jack Mostow
- 年份：1994
- 出版日期：1994-04-01
- 类型：article
- 语言：en
- 来源：Machine Learning
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0885-6125
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1023/a:1022613220324
- OpenAlex ID：https://openalex.org/W2041734073
- 落地页：https://doi.org/10.1023/a:1022613220324
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1023/A:1022613220324.pdf
- 主主题：AI-based Problem Solving and Planning
- 主题：AI-based Problem Solving and Planning, Reservoir Engineering and Simulation Methods, Machine Learning and Algorithms
- 关键词：Pruning, Computer science, Heuristics, Heuristic, Solver, Problem solver, Space (punctuation), State space, Path (computing), Search problem, Artificial intelligence, Algorithm, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16906. Randomized binary search technique

- 标题：Randomized binary search technique
- 作者：S. R. Arora, Warren T. Dent
- 年份：1969
- 出版日期：1969-02-01
- 类型：article
- 语言：en
- 来源：Communications of the ACM
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：0001-0782
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1145/362848.362856
- OpenAlex ID：https://openalex.org/W2045283155
- 落地页：https://doi.org/10.1145/362848.362856
- 开放 PDF 链接：https://dl.acm.org/doi/pdf/10.1145/362848.362856
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Algorithms and Data Compression, Optimization and Search Problems
- 关键词：Binary number, Computer science, Variance (accounting), Binary search algorithm, Binary search tree, Information retrieval, Binary data, Algorithm, Search algorithm, Mathematics, Arithmetic, Binary tree
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A mathematical model is developed for the mean and variance of the number of trials to recover a given document in a randomly received list of files. The search method described is binary in nature and offers new potential for information retrieval systems.

## 16907. Learning fuzzy decision trees

- 标题：Learning fuzzy decision trees
- 作者：Bruno Apolloni, Giacomo Zamponi, Anna Maria Zanaboni
- 年份：1998
- 出版日期：1998-07-01
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/s0893-6080(98)00030-6
- OpenAlex ID：https://openalex.org/W2054788007
- 落地页：https://doi.org/10.1016/s0893-6080(98)00030-6
- 主主题：Fuzzy Logic and Control Systems
- 主题：Fuzzy Logic and Control Systems, Machine Learning and Algorithms, Neural Networks and Applications
- 关键词：Computer science, Decision tree, Node (physics), Artificial intelligence, Set (abstract data type), Tree (set theory), Sequence (biology), Incremental decision tree, Task (project management), Artificial neural network, Core (optical fiber), Fuzzy logic, Machine learning, Decision tree learning, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16908. An Optimality Property of Scheffe Bounds

- 标题：An Optimality Property of Scheffe Bounds
- 作者：Robert Bohrer
- 年份：1973
- 出版日期：1973-07-01
- 类型：article
- 语言：en
- 来源：The Annals of Statistics
- 来源类型：journal
- 出版方：Institute of Mathematical Statistics
- ISSN-L：0090-5364
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：bronze
- DOI：10.1214/aos/1176342473
- OpenAlex ID：https://openalex.org/W2082487892
- 落地页：https://doi.org/10.1214/aos/1176342473
- 开放 PDF 链接：https://projecteuclid.org/journals/annals-of-statistics/volume-1/issue-4/An-Optimality-Property-of-Scheffe-Bounds/10.1214/aos/1176342473.pdf
- 主主题：Multi-Criteria Decision Making
- 主题：Multi-Criteria Decision Making, Machine Learning and Algorithms, Statistical Methods and Inference
- 关键词：Scheffé's method, Mathematics, Confidence interval, Property (philosophy), Statistics, Confidence region, Applied mathematics, Combinatorics, Analysis of variance
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Conditions are derived which are commonly met in applications and which are sufficient for both one- and two-sided Scheffe bounds to have no greater average width than any other-shaped confidence bounds which have the same confidence coefficient.

## 16909. A PROGRAM FOR RECONSTRUCTABILUY ANALYSIS

- 标题：A PROGRAM FOR RECONSTRUCTABILUY ANALYSIS
- 作者：Bush Jones
- 年份：1989
- 出版日期：1989-08-01
- 类型：article
- 语言：en
- 来源：International Journal of General Systems
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0308-1079
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1080/03081078908935045
- OpenAlex ID：https://openalex.org/W2090066031
- 落地页：https://doi.org/10.1080/03081078908935045
- 主主题：Fault Detection and Control Systems
- 主题：Fault Detection and Control Systems, Neural Networks and Applications, Machine Learning and Algorithms
- 关键词：Computer science, Program analysis, Theoretical computer science, Data mining, Operations research, Programming language, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract This paper describes a program to solve the reconstruction problem of reconstructability analysis. The program can be utilized to solve numerous data analysis problems, and it is available from the author. The program provides potent information on a system in the form of descriptive factors or substates, which can be used to reproduce the system. Algorilhms from previously published papers are presented here in a collective and coherent form and some new techniques are introduced.

## 16910. Aladdin: Assembly Language Assertion Driven Debugging Interpreter

- 标题：Aladdin: Assembly Language Assertion Driven Debugging Interpreter
- 作者：Richard E. Fairley
- 年份：1979
- 出版日期：1979-07-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Software Engineering
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：0098-5589
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tse.1979.230176
- OpenAlex ID：https://openalex.org/W2099818851
- 落地页：https://doi.org/10.1109/tse.1979.230176
- 主主题：Software Testing and Debugging Techniques
- 主题：Software Testing and Debugging Techniques, Adversarial Robustness in Machine Learning, Software Engineering Research
- 关键词：Debugging, Assertion, Computer science, Programming language, Interpreter, State (computer science), Assembly language, Object (grammar), Software, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
ALADDIN is an interactive facility for debugging and testing of assembly language programs. ALADDIN differs from traditional debuggers by allowing the user to specify breakpoint assertions, rather than breakpoint locations. Assertions are logical relations among various components of the program state. If an assertion becomes false during execution of the object program a breakpoint is executed and control is passed to the user's terminal. ALADDIN can also be used as a testing tool to verify that asserted behavior matches actual behavior under various sets of input data and test conditions.

## 16911. Derivatives of Tree Sets with Applications to Grammatical Inference

- 标题：Derivatives of Tree Sets with Applications to Grammatical Inference
- 作者：Barry A. Levine
- 年份：1981
- 出版日期：1981-05-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Pattern Analysis and Machine Intelligence
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：0162-8828
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tpami.1981.4767101
- OpenAlex ID：https://openalex.org/W2137024331
- 落地页：https://doi.org/10.1109/tpami.1981.4767101
- 主主题：semigroups and automata theory
- 主题：semigroups and automata theory, Machine Learning and Algorithms, Natural Language Processing Techniques
- 关键词：Tree automaton, Tree (set theory), Automaton, ω-automaton, Quantum finite automata, Computer science, Automata theory, Deterministic automaton, Timed automaton, Theoretical computer science, Nondeterministic finite automaton, Inference, Deterministic finite automaton, Algorithm, K-ary tree, Mathematics, Tree structure, Combinatorics, Artificial intelligence, Binary tree
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Tree automata generalize the notion of a finite automaton working on strings to that of a finite automaton operating on trees. Most results for finite automata have been extended to tree automata. In this paper we introduce tree derivatives which extend the concept of Brzozowski's string derivatives. We use tree derivatives for minimizing and characterizing tree automata. Tree derivatives are used as a basis of inference of tree automata from finite samples of trees. Our method compares tree derivative sets and infers a tree automaton based on the amount of overlap between the derivative sets. Several of the limitations present in the tree inference techniques by Brayer and Fu and Edwards, Gonzalez, and Thomason are not imposed by our algorithm.

## 16912. New nonleast-squares neural network learning algorithms for hypothesis testing

- 标题：New nonleast-squares neural network learning algorithms for hypothesis testing
- 作者：Dimitris A. Pados, P. Papantoni‐Kazakos
- 年份：1995
- 出版日期：1995-05-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Neural Networks
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1045-9227
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/72.377966
- OpenAlex ID：https://openalex.org/W2165986722
- 落地页：https://doi.org/10.1109/72.377966
- 主主题：Fault Detection and Control Systems
- 主题：Fault Detection and Control Systems, Machine Learning and Algorithms, Neural Networks and Applications
- 关键词：Algorithm, Computer science, Backpropagation, Artificial neural network, Artificial intelligence, Perceptron, Machine learning, Statistical hypothesis testing, Feedforward neural network, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Hypothesis testing is a collective name for problems such as classification, detection, and pattern recognition. In this paper we propose two new classes of supervised learning algorithms for feedforward, binary-output neural network structures whose objective is hypothesis testing. All the algorithms are applications of stochastic approximation and are guaranteed to provide optimization with probability one. The first class of algorithms follows the Neyman-Pearson approach and maximizes the probability of detection, subject to a given false alarm constraint. These algorithms produce layer-by-layer optimal Neyman-Pearson designs. The second class of algorithms minimizes the probability of error and leads to layer-by-layer Bayes optimal designs. Deviating from the layer-by-layer optimization assumption, we propose more powerful learning techniques which unify, in some sense, the already existing algorithms. The proposed algorithms were implemented and tested on a simulated hypothesis testing problem. Backpropagation and perceptron learning were also included in the comparisons.

## 16913. Using Augmented Statistical Models and Score Spaces for Classification

- 标题：Using Augmented Statistical Models and Score Spaces for Classification
- 作者：N. D. Smith
- 年份：2003
- 出版日期：2003-01-01
- 类型：article
- 语言：en
- 来源：Medical Entomology and Zoology
- 来源类型：journal
- 出版方：Japan Society of Medical Entomology and Zoology
- ISSN-L：0424-7086
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1001/jamainternmed.2023.1242
- OpenAlex ID：https://openalex.org/W37184870
- 落地页：http://ci.nii.ac.jp/naid/10015194883/en/
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Machine Learning and Data Classification, Advanced Statistical Methods and Models
- 关键词：Artificial intelligence, Computer science, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16914. Inferring depictions in natural-language captions for efficient access to picture data

- 标题：Inferring depictions in natural-language captions for efficient access to picture data
- 作者：Neil C. Rowe
- 年份：1994
- 出版日期：1994-05-01
- 类型：article
- 语言：en
- 来源：Information Processing & Management
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0306-4573
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/0306-4573(94)90051-5
- OpenAlex ID：https://openalex.org/W2025160544
- 落地页：https://doi.org/10.1016/0306-4573(94)90051-5
- 主主题：Video Analysis and Summarization
- 主题：Video Analysis and Summarization, Natural Language Processing Techniques, Multimodal Machine Learning Applications
- 关键词：Computer science, Depiction, Natural language processing, Natural language, Artificial intelligence, Inference, Natural (archaeology), Matching (statistics), Information retrieval, Linguistic analysis, Linguistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16915. Exploiting captions in retrieval of multimedia data

- 标题：Exploiting captions in retrieval of multimedia data
- 作者：Neil C. Rowe, Eugene J. Guglielmo
- 年份：1993
- 出版日期：1993-07-01
- 类型：article
- 语言：en
- 来源：Information Processing & Management
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0306-4573
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/0306-4573(93)90041-b
- OpenAlex ID：https://openalex.org/W2043985578
- 落地页：https://doi.org/10.1016/0306-4573(93)90041-b
- 主主题：Video Analysis and Summarization
- 主题：Video Analysis and Summarization, Natural Language Processing Techniques, Multimodal Machine Learning Applications
- 关键词：Computer science, Information retrieval, Redundancy (engineering), Exploit, Hierarchy, Natural language, Matching (statistics), Data retrieval, Document retrieval, Natural language processing, Multimedia, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16916. On-line learning of non-monotonic rules by simple perceptron

- 标题：On-line learning of non-monotonic rules by simple perceptron
- 作者：Jun-ichi Inoue, Hidetoshi Nishimori, Yoshiyuki Kabashima
- 年份：1997
- 出版日期：1997-06-07
- 类型：article
- 语言：en
- 来源：Journal of Physics A Mathematical and General
- 来源类型：journal
- 出版方：Institute of Physics
- ISSN-L：0305-4470
- OpenAlex 引用数：23
- 开放获取：是
- OA 状态：green
- DOI：10.1088/0305-4470/30/11/012
- OpenAlex ID：https://openalex.org/W2047873276
- 落地页：https://doi.org/10.1088/0305-4470/30/11/012
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Machine Learning and Algorithms, Stochastic Gradient Optimization Techniques
- 关键词：Generalization, Perceptron, Generalization error, Simple (philosophy), Probably approximately correct learning, Multilayer perceptron
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
We study the generalization ability of a simple perceptron which learns unlearnable rules. The rules are presented by a teacher perceptron with a non-monotonic transfer function. The student is trained in the on-line mode. The asymptotic behaviour of the generalization error is estimated under various conditions. Several learning strategies are proposed and improved to obtain the theoretical lower bound of the generalization error.

## 16917. Synthesizing inductive expertise

- 标题：Synthesizing inductive expertise
- 作者：Daniel N. Osherson, Michael Stob, Scott A. Weinstein
- 年份：1988
- 出版日期：1988-05-01
- 类型：article
- 语言：en
- 来源：Information and Computation
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0890-5401
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/0890-5401(88)90055-7
- OpenAlex ID：https://openalex.org/W2059655876
- 落地页：https://doi.org/10.1016/0890-5401(88)90055-7
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Computability, Logic, AI Algorithms, Algorithms and Data Compression
- 关键词：Inductive reasoning, Computer science, Recursion (computer science), Perspective (graphical), Inference, Inductive method, Theoretical computer science, Programming language, Artificial intelligence, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16918. Stochastic dynamics of supervised learning

- 标题：Stochastic dynamics of supervised learning
- 作者：Lars Kai Hansen, R. K. Pathria, Peter Salamon
- 年份：1993
- 出版日期：1993-01-07
- 类型：article
- 语言：en
- 来源：Journal of Physics A Mathematical and General
- 来源类型：journal
- 出版方：Institute of Physics
- ISSN-L：0305-4470
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1088/0305-4470/26/1/011
- OpenAlex ID：https://openalex.org/W2086420260
- 落地页：https://doi.org/10.1088/0305-4470/26/1/011
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Statistical Mechanics and Entropy, Machine Learning and Algorithms
- 关键词：Backpropagation, Statistical physics, Fokker–Planck equation, Artificial neural network, Dimension (graph theory), Isotropy, Mathematics, Distribution (mathematics), Applied mathematics, Artificial intelligence, Computer science, Mathematical analysis, Physics, Differential equation, Quantum mechanics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The stochastic evolution of adiabatic (slow) backpropagation training of a neural network is discussed and a Fokker-Planck equation for the post-training distribution function in the network space is derived. The distribution obtained differs from the one given by Radons et al. (1990). Studying the character of the post-training distribution, the authors find that, except under very special circumstances, the distribution will be non-Gibbsian. The validity of the present approach is tested on a simple backpropagation learning system in one dimension, which can be solved analytically as well. Implications of the Fokker-Planck approach for general situations are examined in the local linear approximation. Surprisingly they find that the post-training distribution is isotropic close to its peak, hence simpler than the corresponding Gibbs distribution.

## 16919. Fast Search Algorithms for Associative Memories

- 标题：Fast Search Algorithms for Associative Memories
- 作者：Davis, De-Lei Lee
- 年份：1986
- 出版日期：1986-05-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Computers
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9340
- OpenAlex 引用数：23
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tc.1986.1676788
- OpenAlex ID：https://openalex.org/W2156147449
- 落地页：https://doi.org/10.1109/tc.1986.1676788
- 主主题：Algorithms and Data Compression
- 主题：Algorithms and Data Compression, Machine Learning and Algorithms, DNA and Biological Computing
- 关键词：Content-addressable memory, Algorithm, Computer science, Associative property, Limit (mathematics), Binary logarithm, Equivalence (formal languages), Arithmetic, Mathematics, Discrete mathematics, Artificial neural network, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
A new scheme for constructing search algorithms for bit-parallel associative memories of m n-bit words is described. The resulting equivalence searches, threshold searches, and double-limit searches achieve the time bound of O(log n), compared to O(n), the recent result of Ramamoorthy et al. [12]. The extremum search algorithm by Frei and Goldberg [2] is modified and generalized so that the number of memory interrogations is reduced by 30 percent over the initial algorithm in the average case.

## 16920. Objective clustering inductive technology of gene expression profiles based on sota clustering algorithm

- 标题：Objective clustering inductive technology of gene expression profiles based on sota clustering algorithm
- 作者：Sergii Babichev, Aleksandr Gozhyj, A. I. Kornelyuk, Volodymyr Lytvynenko
- 年份：2017
- 出版日期：2017-10-31
- 类型：article
- 语言：en
- 来源：Biopolymers and Cell
- 来源类型：journal
- 出版方：Institute of Molecular Biology and Genetics of NASU
- ISSN-L：0233-7657
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：diamond
- DOI：10.7124/bc.000961
- OpenAlex ID：https://openalex.org/W2784321730
- 落地页：https://doi.org/10.7124/bc.000961
- 开放 PDF 链接：http://www.biopolymers.org.ua/pdf/en/33/5/379/biopolym.cell-2017-33-5-379-en.pdf
- 主主题：Gene expression and cancer classification
- 主题：Gene expression and cancer classification, Face and Expression Recognition, Machine Learning and Data Classification
- 关键词：Cluster analysis, Computer science, Data mining, Computational biology, Algorithm, Artificial intelligence, Biology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
aim. Development of an inductive technology of objective clustering of gene expression profiles based on a self-organizing SOTA clustering algorithm. Methods. Inductive methods of complex system analysis were used to implement the inductive technology of objective clustering of gene expression profiles. The optimal parameters of clustering algorithm were estimated using internal clustering quality criteria, external criteria and complex balance criteria. Results. Here we present the architecture of the inductive technology of objective clustering based on SOTA clustering algorithm and step-by-step procedure of its implementation. Charts of the internal, external and complex balance criteria versus the algorithm parameters were obtained during simulation. This allowed us to determine the optimal parameters of the algorithm. Conclusion. We have shown a high efficiency of the proposed technology. In case of analysis of gene expression profiles, this approach allows to implement a step-by-step cluster-bicluster technology of data grouping at an early stage of gene regulatory network reconstruction.

## 16921. Nearly Minimax One-Sided Mixture-Based Sequential Tests

- 标题：Nearly Minimax One-Sided Mixture-Based Sequential Tests
- 作者：Georgios Fellouris, Alexander G. Tartakovsky
- 年份：2012
- 出版日期：2012-07-01
- 类型：article
- 语言：en
- 来源：Sequential Analysis
- 来源类型：journal
- 出版方：Taylor & Francis
- ISSN-L：0747-4946
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1080/07474946.2012.694346
- OpenAlex ID：https://openalex.org/W2962714136
- 落地页：https://doi.org/10.1080/07474946.2012.694346
- 主主题：Advanced Statistical Process Monitoring
- 主题：Advanced Statistical Process Monitoring, Statistical Methods in Clinical Trials, Machine Learning and Algorithms
- 关键词：Minimax, Mathematics, Exponential family, Sequential estimation, Simple (philosophy), Bayes' theorem, Sequential analysis, Optimal stopping, Stopping time, Stopping rule, Applied mathematics, Exponential function, Decision rule, Mathematical optimization, Bayesian probability, Statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract We focus on one-sided, mixture-based stopping rules for the problem of sequential testing a simple null hypothesis against a composite alternative. For the latter, we consider two cases—either a discrete alternative or a continuous alternative that can be embedded into an exponential family. For each case, we find a mixture-based stopping rule that is nearly minimax in the sense of minimizing the maximal Kullback–Leibler information. The proof of this result is based on finding an almost Bayes rule for an appropriate sequential decision problem and on high-order asymptotic approximations for the performance characteristics of arbitrary mixture-based stopping times. We also evaluate the asymptotic performance loss of certain intuitive mixture rules and verify the accuracy of our asymptotic approximations with simulation experiments.

## 16922. Adversarial transfer learning for cross-domain visual recognition

- 标题：Adversarial transfer learning for cross-domain visual recognition
- 作者：Shanshan Wang, Lei Zhang, Jingru Fu
- 年份：2020
- 出版日期：2020-07-15
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2020.106258
- OpenAlex ID：https://openalex.org/W3043085410
- 落地页：https://doi.org/10.1016/j.knosys.2020.106258
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Machine Learning and ELM, Multimodal Machine Learning Applications
- 关键词：Computer science, Transfer of learning, Artificial intelligence, Domain (mathematical analysis), Benchmark (surveying), Adversarial system, Feature (linguistics), Machine learning, Perceptron, Pattern recognition (psychology), Generator (circuit theory), Artificial neural network, Power (physics), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16923. Metainduction over Unboundedly Many Prediction Methods: A Reply to Arnold and Sterkenburg

- 标题：Metainduction over Unboundedly Many Prediction Methods: A Reply to Arnold and Sterkenburg
- 作者：Gerhard Schurz
- 年份：2020
- 出版日期：2020-09-10
- 类型：article
- 语言：en
- 来源：Philosophy of Science
- 来源类型：journal
- 出版方：Cambridge University Press
- ISSN-L：0031-8248
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1086/711587
- OpenAlex ID：https://openalex.org/W3084685860
- 落地页：https://doi.org/10.1086/711587
- 主主题：Advanced Bandit Algorithms Research
- 主题：Advanced Bandit Algorithms Research, Machine Learning and Algorithms, Computability, Logic, AI Algorithms
- 关键词：Equivalence (formal languages), Mathematics, Mathematical economics, Computer science, Discrete mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The universal optimality theorem for metainduction works for epistemic agents faced with a choice among finitely many prediction methods. Eckhart Arnold and Tom Sterkenburg objected that it breaks down for infinite or unboundedly growing sets of methods. In this article the metainductive approach is defended against this challenge by extending the optimality theorem (i) to unboundedly growing sets of methods whose number grows less than exponentially in time, (ii) to sequences of methods with an application to Goodman's problem, and (iii) to infinite sets of methods whose number of predictive equivalence classes grows less than linearly in time.

## 16924. Algorithmic fog of war: When lack of transparency violates the law of armed conflict

- 标题：Algorithmic fog of war: When lack of transparency violates the law of armed conflict
- 作者：Jonathan Kwik, Tom van Engers
- 年份：2021
- 出版日期：2021-03-12
- 类型：article
- 语言：en
- 来源：Journal of Future Robot Life
- 来源类型：journal
- 出版方：IOS Press
- ISSN-L：2589-9953
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：diamond
- DOI：10.3233/frl-200019
- OpenAlex ID：https://openalex.org/W3138982240
- 落地页：https://doi.org/10.3233/frl-200019
- 开放 PDF 链接：https://content.iospress.com:443/download/journal-of-future-robot-life/frl200019?id=journal-of-future-robot-life%2Ffrl200019
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Explainable Artificial Intelligence (XAI), Ethics and Social Impacts of AI
- 关键词：Transparency (behavior), Software deployment, Incentive, International humanitarian law, Computer security, Law, Business, Law and economics, Computer science, International law, Political science, Economics, Microeconomics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Under international law, weapon capabilities and their use are regulated by legal requirements set by International Humanitarian Law (IHL). Currently, there are strong military incentives to equip capabilities with increasingly advanced artificial intelligence (AI), which include opaque (less transparent) models. As opaque models sacrifice transparency for performance, it is necessary to examine whether their use remains in conformity with IHL obligations. First, we demonstrate that the incentives for automation drive AI toward complex task areas and dynamic and unstructured environments, which in turn necessitates resort to more opaque solutions. We subsequently discuss the ramifications of opaque models for foreseeability and explainability. Then, we analyse their impact on IHL requirements from a development, pre-deployment and post-deployment perspective. We find that while IHL does not regulate opaque AI directly, the lack of foreseeability and explainability frustrates the fulfilment of key IHL requirements to the extent that the use of fully opaque AI could violate international law. States are urged to implement interpretability during development and seriously consider the challenging complication of determining the appropriate balance between transparency and performance in their capabilities.

## 16925. Universal Consistency of Deep Convolutional Neural Networks

- 标题：Universal Consistency of Deep Convolutional Neural Networks
- 作者：Shao-Bo Lin, Kaidong Wang, Yao Wang, Ding‐Xuan Zhou
- 年份：2022
- 出版日期：2022-02-16
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Theory
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9448
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tit.2022.3151753
- OpenAlex ID：https://openalex.org/W3173445760
- 落地页：https://doi.org/10.1109/tit.2022.3151753
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Ferroelectric and Negative Capacitance Devices, Advancements in Semiconductor Devices and Circuit Design
- 关键词：Convolutional neural network, Convolution (computer science), Consistency (knowledge bases), Expansive, Computer science, Padding, Artificial intelligence, Deep learning, Algorithm, Theoretical computer science, Artificial neural network, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Compared with avid research activities of deep convolutional neural networks (DCNNs) in practice, the study of theoretical behaviors of DCNNs lags heavily behind. In particular, the universal consistency of DCNNs remains open. In this paper, we prove that implementing empirical risk minimization on DCNNs with expansive convolution (with zero-padding) is strongly universally consistent. Motivated by the universal consistency, we conduct a series of experiments to show that without any fully connected layers, DCNNs with expansive convolution perform not worse than the widely used deep neural networks with hybrid structure containing contracting (without zero-padding) convolutional layers and several fully connected layers.

## 16926. Predicting carcass cut yields in cattle from digital images using artificial intelligence

- 标题：Predicting carcass cut yields in cattle from digital images using artificial intelligence
- 作者：D. Matthews, T. Pabiou, R.D. Evans, Christian Beder, Aengus Daly
- 年份：2021
- 出版日期：2021-09-10
- 类型：article
- 语言：en
- 来源：Meat Science
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0309-1740
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.meatsci.2021.108671
- OpenAlex ID：https://openalex.org/W3199593493
- 落地页：https://doi.org/10.1016/j.meatsci.2021.108671
- 主主题：Genetic and phenotypic traits in livestock
- 主题：Genetic and phenotypic traits in livestock, Machine Learning and Data Classification, Generative Adversarial Networks and Image Synthesis
- 关键词：Artificial intelligence, Pattern recognition (psychology), Convolutional neural network, Artificial neural network, Carcass weight, Range (aeronautics), Deep learning, Computer science, Mathematics, Biology, Body weight, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16927. Hidden Markov and Semi-Markov Models When and Why are These Models Useful for Classifying States in Time Series Data?

- 标题：Hidden Markov and Semi-Markov Models When and Why are These Models Useful for Classifying States in Time Series Data?
- 作者：Sofía Ruiz‐Suarez, Vianey Leos‐Barajas, Juan M. Morales
- 年份：2022
- 出版日期：2022-01-17
- 类型：article
- 语言：en
- 来源：Journal of Agricultural Biological and Environmental Statistics
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1085-7117
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s13253-021-00483-x
- OpenAlex ID：https://openalex.org/W4205892261
- 落地页：https://doi.org/10.1007/s13253-021-00483-x
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Genetic and phenotypic traits in livestock, Fish Ecology and Management Studies
- 关键词：Hidden Markov model, Autoregressive model, Computer science, Artificial intelligence, Context (archaeology), Hidden semi-Markov model, Machine learning, Markov model, Markov chain, Time series, Pattern recognition (psychology), Data mining, Variable-order Markov model, Econometrics, Mathematics, Geography
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16928. Rethinking ResNets: improved stacking strategies with high-order schemes for image classification

- 标题：Rethinking ResNets: improved stacking strategies with high-order schemes for image classification
- 作者：Zhengbo Luo, Zitang Sun, Weilian Zhou, Zizhang Wu, Sei‐ichiro Kamata
- 年份：2022
- 出版日期：2022-02-22
- 类型：article
- 语言：en
- 来源：Complex & Intelligent Systems
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：2198-6053
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1007/s40747-022-00671-3
- OpenAlex ID：https://openalex.org/W4213058744
- 落地页：https://doi.org/10.1007/s40747-022-00671-3
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s40747-022-00671-3.pdf
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Adversarial Robustness in Machine Learning, Domain Adaptation and Few-Shot Learning
- 关键词：Stacking, Robustness (evolution), Computer science, Residual, Artificial neural network, Residual neural network, Euler's formula, Computer engineering, Differential (mechanical device), Mathematical optimization, Artificial intelligence, Algorithm, Theoretical computer science, Mathematics, Engineering, Mathematical analysis
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Various deep neural network architectures (DNNs) maintain massive vital records in computer vision. While drawing attention worldwide, the design of the overall structure lacks general guidance. Based on the relationship between DNN design and numerical differential equations, we performed a fair comparison of the residual design with higher order perspectives. We show that the widely used DNN design strategy, constantly stacking a small design (usually, 2–3 layers), could be easily improved, supported by solid theoretical knowledge and with no extra parameters needed. We reorganise the residual design in higher order ways, which is inspired by the observation that many effective networks can be interpreted as different numerical discretisations of differential equations. The design of ResNet follows a relatively simple scheme, which is Euler forward; however, the situation becomes complicated rapidly while stacking. We suppose that stacked ResNet is somehow equalled to a higher order scheme; then, the current method of forwarding propagation might be relatively weak compared with a typical high-order method such as Runge–Kutta. We propose HO-ResNet to verify the hypothesis on widely used CV benchmarks with sufficient experiments. Stable and noticeable increases in performance are observed, and convergence and robustness are also improved. Our stacking strategy improved ResNet-30 by 2.15% and ResNet-58 by 2.35% on CIFAR-10, with the same settings and parameters. The proposed strategy is fundamental and theoretical and can, therefore, be applied to any network as a general guideline. Graphical abstract

## 16929. Detection of Adversarial DDoS Attacks Using Generative Adversarial Networks with Dual Discriminators

- 标题：Detection of Adversarial DDoS Attacks Using Generative Adversarial Networks with Dual Discriminators
- 作者：Chin‐Shiuh Shieh, Thanh-Tuan Nguyen, Wan-Wei Lin, Yong-Lin Huang, Mong‐Fong Horng, Tsair-Fwu Lee, Denis Miu
- 年份：2022
- 出版日期：2022-01-04
- 类型：article
- 语言：en
- 来源：Symmetry
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2073-8994
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/sym14010066
- OpenAlex ID：https://openalex.org/W4225494994
- 落地页：https://doi.org/10.3390/sym14010066
- 开放 PDF 链接：https://www.mdpi.com/2073-8994/14/1/66/pdf?version=1641276775
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Network Security and Intrusion Detection
- 关键词：Denial-of-service attack, Computer science, Trinoo, Application layer DDoS attack, Adversarial system, Computer security, Artificial intelligence, Discriminator, Adversarial machine learning, Machine learning, Computer network, The Internet, World Wide Web
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
DDoS (Distributed Denial of Service) has emerged as a serious and challenging threat to computer networks and information systems’ security and integrity. Before any remedial measures can be implemented, DDoS assaults must first be detected. DDoS attacks can be identified and characterized with satisfactory achievement employing ML (Machine Learning) and DL (Deep Learning). However, new varieties of aggression arise as the technology for DDoS attacks keep evolving. This research explores the impact of a new incarnation of DDoS attack–adversarial DDoS attack. There are established works on ML-based DDoS detection and GAN (Generative Adversarial Network) based adversarial DDoS synthesis. We confirm these findings in our experiments. Experiments in this study involve the extension and application of the GAN, a machine learning framework with symmetric form having two contending neural networks. We synthesize adversarial DDoS attacks utilizing Wasserstein Generative Adversarial Networks featuring Gradient Penalty (GP-WGAN). Experiment results indicate that the synthesized traffic can traverse the detection systems such as k-Nearest Neighbor (KNN), Multi-Layer Perceptron (MLP) and Random Forest (RF) without being identified. This observation is a sobering and pessimistic wake-up call, implying that countermeasures to adversarial DDoS attacks are urgently needed. To this problem, we propose a novel DDoS detection framework featuring GAN with Dual Discriminators (GANDD). The additional discriminator is designed to identify adversary DDoS traffic. The proposed GANDD can be an effective solution to adversarial DDoS attacks, as evidenced by the experimental results. We use adversarial DDoS traffic synthesized by GP-WGAN to train GANDD and validate it alongside three other DL technologies: DNN (Deep Neural Network), LSTM (Long Short-Term Memory) and GAN. GANDD outperformed the other DL models, demonstrating its protection with a TPR of 84.3%. A more sophisticated test was also conducted to examine GANDD’s ability to handle unseen adversarial attacks. GANDD was evaluated with adversarial traffic not generated from its training data. GANDD still proved effective with a TPR around 71.3% compared to 7.4% of LSTM.

## 16930. IEEE Transactions on Emerging Topics in Computational Intelligence

- 标题：IEEE Transactions on Emerging Topics in Computational Intelligence
- 作者：Yew-Soon Ong, Oscar Cordon, Huanhuan Chen, Keeley Crockett, K Chi-Keong, Goh Yoozoo, Abhishek Gupta, Amir Hussain, K Konar, Yun Li, Amiram Moshaiov, Vladimir Pavlovic
- 年份：2019
- 出版日期：2019-03-25
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Emerging Topics in Computational Intelligence
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2471-285X
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：bronze
- DOI：10.1109/tetci.2019.2902895
- OpenAlex ID：https://openalex.org/W4237638342
- 落地页：https://doi.org/10.1109/tetci.2019.2902895
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/7433297/8673683/08673695.pdf
- 主主题：Internet of Things and AI
- 主题：Internet of Things and AI, Big Data and Digital Economy, Machine Learning and Algorithms
- 关键词：Computer science, Data science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16931. A precise high-dimensional asymptotic theory for boosting and minimum-ℓ1-norm interpolated classifiers

- 标题：A precise high-dimensional asymptotic theory for boosting and minimum-ℓ1-norm interpolated classifiers
- 作者：Tengyuan Liang, Pragya Sur
- 年份：2022
- 出版日期：2022-06-01
- 类型：article
- 语言：en
- 来源：The Annals of Statistics
- 来源类型：journal
- 出版方：Institute of Mathematical Statistics
- ISSN-L：0090-5364
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1214/22-aos2170
- OpenAlex ID：https://openalex.org/W4283031248
- 落地页：https://doi.org/10.1214/22-aos2170
- 主主题：Statistical Methods and Inference
- 主题：Statistical Methods and Inference, Sparse and Compressive Sensing Techniques, Machine Learning and Algorithms
- 关键词：Mathematics, Boosting (machine learning), Applied mathematics, Statistical hypothesis testing, Large deviations theory, Algorithm, Statistics, Artificial intelligence, Computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This paper establishes a precise high-dimensional asymptotic theory for boosting on separable data, taking statistical and computational perspectives. We consider a high-dimensional setting where the number of features (weak learners) p scales with the sample size n, in an overparametrized regime. Under a class of statistical models, we provide an exact analysis of the generalization error of boosting when the algorithm interpolates the training data and maximizes the empirical ℓ1-margin. Further, we explicitly pin down the relation between the boosting test error and the optimal Bayes error, as well as the proportion of active features at interpolation (with zero initialization). In turn, these precise characterizations answer certain questions raised in (Neural Comput. 11 (1999) 1493–1517; Ann. Statist. 26 (1998) 1651–1686) surrounding boosting, under assumed data generating processes. At the heart of our theory lies an in-depth study of the maximum-ℓ1-margin, which can be accurately described by a new system of nonlinear equations; to analyze this margin, we rely on Gaussian comparison techniques and develop a novel uniform deviation argument. Our statistical and computational arguments can handle (1) any finite-rank spiked covariance model for the feature distribution and (2) variants of boosting corresponding to general ℓq-geometry, q∈[1,2]. As a final component, via the Lindeberg principle, we establish a universality result showcasing that the scaled ℓ1-margin (asymptotically) remains the same, whether the covariates used for boosting arise from a nonlinear random feature model or an appropriately linearized model with matching moments.

## 16932. Privacy-Preserving and Explainable AI in Industrial Applications

- 标题：Privacy-Preserving and Explainable AI in Industrial Applications
- 作者：Iulian Alexandru Ogrezeanu, Anamaria Vizitiu, Costin Ciușdel, A. Puiu, Simona M. Coman, Cristian Boldișor, Alina Itu, Róbert Demeter, Florin Moldoveanu, Constantin Suciu, Lucian Itu
- 年份：2022
- 出版日期：2022-06-23
- 类型：article
- 语言：en
- 来源：Applied Sciences
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2076-3417
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/app12136395
- OpenAlex ID：https://openalex.org/W4283373744
- 落地页：https://doi.org/10.3390/app12136395
- 开放 PDF 链接：https://www.mdpi.com/2076-3417/12/13/6395/pdf?version=1656061552
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Explainable Artificial Intelligence (XAI), Anomaly Detection Techniques and Applications
- 关键词：Industrial Internet, Computer science, Industry 4.0, Process (computing), Computer security, Risk analysis (engineering), Data science, Internet of Things, Data mining, Business
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The industrial environment has gone through the fourth revolution, also called “Industry 4.0”, where the main aspect is digitalization. Each device employed in an industrial process is connected to a network called the industrial Internet of things (IIOT). With IIOT manufacturers being capable of tracking every device, it has become easier to prevent or quickly solve failures. Specifically, the large amount of available data has allowed the use of artificial intelligence (AI) algorithms to improve industrial applications in many ways (e.g., failure detection, process optimization, and abnormality detection). Although data are abundant, their access has raised problems due to privacy concerns of manufacturers. Censoring sensitive information is not a desired approach because it negatively impacts the AI performance. To increase trust, there is also the need to understand how AI algorithms make choices, i.e., to no longer regard them as black boxes. This paper focuses on recent advancements related to the challenges mentioned above, discusses the industrial impact of proposed solutions, and identifies challenges for future research. It also presents examples related to privacy-preserving and explainable AI solutions, and comments on the interaction between the identified challenges in the conclusions.

## 16933. Adversarial image perturbations with distortions weighted by color on deep neural networks

- 标题：Adversarial image perturbations with distortions weighted by color on deep neural networks
- 作者：Hyun Kwon
- 年份：2022
- 出版日期：2022-10-03
- 类型：article
- 语言：en
- 来源：Multimedia Tools and Applications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1380-7501
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11042-022-12941-w
- OpenAlex ID：https://openalex.org/W4300960660
- 落地页：https://doi.org/10.1007/s11042-022-12941-w
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Integrated Circuits and Semiconductor Failure Analysis, Electrostatic Discharge in Electronics
- 关键词：Computer science, Adversarial system, Distortion (music), Artificial intelligence, Deep neural networks, Artificial neural network, Image (mathematics), Sample (material), Pattern recognition (psychology), Deep learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16934. Fair detection of poisoning attacks in federated learning on non-i.i.d. data

- 标题：Fair detection of poisoning attacks in federated learning on non-i.i.d. data
- 作者：Ashneet Khandpur Singh, Alberto Blanco-Justicia, Josep Domingo‐Ferrer
- 年份：2023
- 出版日期：2023-01-04
- 类型：article
- 语言：en
- 来源：Data Mining and Knowledge Discovery
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1384-5810
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：bronze
- DOI：10.1007/s10618-022-00912-6
- OpenAlex ID：https://openalex.org/W4313595282
- 落地页：https://doi.org/10.1007/s10618-022-00912-6
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s10618-022-00912-6.pdf
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Adversarial Robustness in Machine Learning, Cryptography and Data Security
- 关键词：Computer science, Computer security, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16935. Adversarial Artificial Intelligence in Insurance: From an Example to Some Potential Remedies

- 标题：Adversarial Artificial Intelligence in Insurance: From an Example to Some Potential Remedies
- 作者：Behnaz Amerirad, Matteo Cattaneo, Ron S. Kenett, Elisa Luciano
- 年份：2023
- 出版日期：2023-01-11
- 类型：article
- 语言：en
- 来源：Risks
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2227-9091
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/risks11010020
- OpenAlex ID：https://openalex.org/W4315786905
- 落地页：https://doi.org/10.3390/risks11010020
- 开放 PDF 链接：https://www.mdpi.com/2227-9091/11/1/20/pdf?version=1674030291
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Autopsy Techniques and Outcomes, Ethics and Social Impacts of AI
- 关键词：Underwriting, Adversarial system, Intermediary, Actuarial science, Business, Robustness (evolution), Taxonomy (biology), Financial services, Computer science, Artificial intelligence, Finance
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Artificial intelligence (AI) is a tool that financial intermediaries and insurance companies use or are willing to use in almost all their activities. AI can have a positive impact on almost all aspects of the insurance value chain: pricing, underwriting, marketing, claims management, and after-sales services. While it is very important and useful, AI is not free of risks, including those related to its robustness against so-called adversarial attacks, which are conducted by external entities to misguide and defraud the AI algorithms. The paper is designed to review adversarial AI and to discuss its implications for the insurance sector. We give a taxonomy of adversarial attacks and present an original, fully fledged example of claims falsification in health insurance, as well as some remedies which are consistent with the current regulatory framework.

## 16936. Improved YOLOX for pedestrian detection in crowded scenes

- 标题：Improved YOLOX for pedestrian detection in crowded scenes
- 作者：Fei Gao, Changxin Cai, Ruohui Jia, Xinzhong Hu
- 年份：2023
- 出版日期：2023-02-28
- 类型：article
- 语言：en
- 来源：Journal of Real-Time Image Processing
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1861-8200
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1007/s11554-023-01287-7
- OpenAlex ID：https://openalex.org/W4322625282
- 落地页：https://doi.org/10.1007/s11554-023-01287-7
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Video Surveillance and Tracking Methods, Multimodal Machine Learning Applications
- 关键词：Intersection (aeronautics), Object detection, Artificial intelligence, Computer science, Recall rate, Pedestrian, Detector, Pedestrian detection, Computer vision, Object (grammar), Precision and recall, Reduction (mathematics), Pattern recognition (psychology), Mathematics, Engineering, Geography, Cartography, Telecommunications
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16937. SCMA: A Scattering Center Model Attack on CNN-SAR Target Recognition

- 标题：SCMA: A Scattering Center Model Attack on CNN-SAR Target Recognition
- 作者：Weibo Qin, Bo Long, Feng Wang
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Geoscience and Remote Sensing Letters
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1545-598X
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/lgrs.2023.3253189
- OpenAlex ID：https://openalex.org/W4323338444
- 落地页：https://doi.org/10.1109/lgrs.2023.3253189
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced SAR Imaging Techniques, Wireless Signal Modulation Classification
- 关键词：Computer science, Interpretability, Convolutional neural network, Synthetic aperture radar, Artificial intelligence, Artificial neural network, Feature extraction, Feature (linguistics), Pattern recognition (psychology), Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Convolutional neural networks (CNNs) have been widely used in SAR (Synthetic Aperture Radar) target recognition, which can extract feature automatically. However, due to its own structural flaws, CNNs are easy to be fooled by adversarial examples, even if they have excellent performance. In this letter, a novel attack named scattering center model attack (SCMA) is designed, and its generation process does not rely on the prior knowledge of any neural network. Therefore, we can get a stable way which can be applied to any neural network. In addition, an improved scattering center model extraction method, which is the pre-part of SCMA, can filter out the useless noise to optimize the stability of attack. In the experiment, SCMA is compared with advanced attack algorithms. From the experimental results, it is clear to find that SCMA has excellent performance in terms of transfer attack success rate. Furthermore, visualization and interpretability analysis underpin the theoretical feasibility of SCMA.

## 16938. What Is a Multi-Modal Knowledge Graph: A Survey

- 标题：What Is a Multi-Modal Knowledge Graph: A Survey
- 作者：Jinghui Peng, Xinyu Hu, Wenbo Huang, Jian Yang
- 年份：2023
- 出版日期：2023-03-14
- 类型：article
- 语言：en
- 来源：Big Data Research
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2214-5796
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.bdr.2023.100380
- OpenAlex ID：https://openalex.org/W4324141351
- 落地页：https://doi.org/10.1016/j.bdr.2023.100380
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Advanced Graph Neural Networks, Topic Modeling
- 关键词：Modal, Computer science, Knowledge graph, Graph, The Internet, Data science, Problem statement, Information retrieval, Artificial intelligence, Theoretical computer science, Data mining, World Wide Web, Engineering, Management science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16939. FastSecNet: An Efficient Cryptographic Framework for Private Neural Network Inference

- 标题：FastSecNet: An Efficient Cryptographic Framework for Private Neural Network Inference
- 作者：Meng Hao, Hongwei Li, Hanxiao Chen, Pengzhi Xing, Tianwei Zhang
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Forensics and Security
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1556-6013
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tifs.2023.3262149
- OpenAlex ID：https://openalex.org/W4360993799
- 落地页：https://doi.org/10.1109/tifs.2023.3262149
- 主主题：Cryptography and Data Security
- 主题：Cryptography and Data Security, Privacy-Preserving Technologies in Data, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Cryptography, Overhead (engineering), Cryptographic protocol, Protocol (science), Secret sharing, Inference, Artificial neural network, Cryptographic primitive, Theoretical computer science, Preprocessor, Encryption, Distributed computing, Computer network, Artificial intelligence, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Private neural network inference has demonstrated great importance in various privacy-critical scenarios. However, the primary challenge remaining in prior works is that the evaluation on encrypted data levies prohibitively high run-time and communication overhead. In this work, we present FastSecNet, an efficient two-party cryptographic framework for private inference in the dealer-based pre-processing setting. Specifically, (1) FastSecNet provides an efficient ReLU protocol for the evalution of non-linear layers, which is built up on a recent advanced cryptographic primitive, function secret sharing (FSS). The core of this construction are an optimized ReLU representation and a customized FSS-based ReLU protocol. (2) For linear layer evaluation, we first propose an efficient PRG-based preprocessing protocol based on the fact that one of the inputs is uniformly random in the offline phase. Then, the online phase only communicates one element and consists of lightweight secret-sharing operations in a ring. Extensive evaluations conducted on 4 real-world datasets and 9 neural network models demonstrate that during the online phase, FastSecNet achieves 14× less runtime and 18× less communication cost compared to the state-of-the-art.

## 16940. FS-BAN: Born-Again Networks for Domain Generalization Few-Shot Classification

- 标题：FS-BAN: Born-Again Networks for Domain Generalization Few-Shot Classification
- 作者：Yunqing Zhao, Ngai‐Man Cheung
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1109/tip.2023.3266172
- OpenAlex ID：https://openalex.org/W4365482845
- 落地页：https://doi.org/10.1109/tip.2023.3266172
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/83/4358840/10102807.pdf
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Machine Learning and Data Classification
- 关键词：Overfitting, Computer science, Generalization, Artificial intelligence, Machine learning, Baseline (sea), Task (project management), Domain (mathematical analysis), Regularization (linguistics), Artificial neural network, Mathematics, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Conventional Few-shot classification (FSC) aims to recognize samples from novel classes given limited labeled data. Recently, domain generalization FSC (DG-FSC) has been proposed with the goal to recognize novel class samples from unseen domains. DG-FSC poses considerable challenges to many models due to the domain shift between base classes (used in training) and novel classes (encountered in evaluation). In this work, we make two novel contributions to tackle DG-FSC. Our first contribution is to propose Born-Again Network (BAN) episodic training and comprehensively investigate its effectiveness for DG-FSC. As a specific form of knowledge distillation, BAN has been shown to achieve improved generalization in conventional supervised classification with a closed-set setup. This improved generalization motivates us to study BAN for DG-FSC, and we show that BAN is promising to address the domain shift encountered in DG-FSC. Building on the encouraging findings, our second (major) contribution is to propose Few-Shot BAN (FS-BAN), a novel BAN approach for DG-FSC. Our proposed FS-BAN includes novel multi-task learning objectives: Mutual Regularization, Mismatched Teacher, and Meta-Control Temperature, each of these is specifically designed to overcome central and unique challenges in DG-FSC, namely overfitting and domain discrepancy. We analyze different design choices of these techniques. We conduct comprehensive quantitative and qualitative analysis and evaluation over six datasets and three baseline models. The results suggest that our proposed FS-BAN consistently improves the generalization performance of baseline models and achieves state-of-the-art accuracy for DG-FSC. Project Page: yunqing-me.github.io/Born-Again-FS/.

## 16941. A framework for inherently interpretable optimization models

- 标题：A framework for inherently interpretable optimization models
- 作者：Marc Goerigk, Michael Hartisch
- 年份：2023
- 出版日期：2023-04-15
- 类型：article
- 语言：en
- 来源：European Journal of Operational Research
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0377-2217
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ejor.2023.04.013
- OpenAlex ID：https://openalex.org/W4365814428
- 落地页：https://doi.org/10.1016/j.ejor.2023.04.013
- 主主题：Explainable Artificial Intelligence (XAI)
- 主题：Explainable Artificial Intelligence (XAI), Machine Learning and Data Classification, Bayesian Modeling and Causal Inference
- 关键词：Interpretability, Generality, Computer science, Univariate, Heuristic, Optimization problem, Mathematical optimization, Machine learning, Decision tree, Artificial intelligence, Integer programming, Software, Tree (set theory), Algorithm, Mathematics, Multivariate statistics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16942. XAI-based cross-ensemble feature ranking methodology for machine learning models

- 标题：XAI-based cross-ensemble feature ranking methodology for machine learning models
- 作者：Pei Jiang, H. Suzuki, Takashi Obi
- 年份：2023
- 出版日期：2023-04-01
- 类型：article
- 语言：en
- 来源：International Journal of Information Technology
- 来源类型：journal
- 出版方：Springer Nature
- ISSN-L：2511-2104
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s41870-023-01270-2
- OpenAlex ID：https://openalex.org/W4367368379
- 落地页：https://doi.org/10.1007/s41870-023-01270-2
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s41870-023-01270-2.pdf
- 主主题：Imbalanced Data Classification Techniques
- 主题：Imbalanced Data Classification Techniques, Explainable Artificial Intelligence (XAI), Machine Learning and Data Classification
- 关键词：Ranking (information retrieval), Computer science, Artificial intelligence, Machine learning, Feature (linguistics), Ensemble learning, Kernel (algebra), Ensemble forecasting, Data mining, Pattern recognition (psychology), Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Artificial Intelligence (AI) as one robust technology has been used in various fields, making innovative society possible and changing our lifestyles. However, the black box problem is still one big problem for artificial intelligence. In this study, we first compared the results of kernel Shapley Additive exPlanations (SHAP) for various machine learning models and found that the single SHAP model cannot explain the models at the human knowledge level. Then the factors’ global ranking was calculated using our proposed ensemble methodology. Finally, the new factors’ ranking was compared with other factor ranking method. Our experimental results declare that the proposed cross-ensemble feature ranking methodology provides stable and comparatively reliable feature ranking in both the classification and regression models.

## 16943. TinyNS: Platform-aware Neurosymbolic Auto Tiny Machine Learning

- 标题：TinyNS: Platform-aware Neurosymbolic Auto Tiny Machine Learning
- 作者：Swapnil Sayan Saha, Sandeep Singh Sandha, Mohit Aggarwal, Brian Wang, Liying Han, Julian de Gortari Briseno, Mani Srivastava
- 年份：2023
- 出版日期：2023-05-31
- 类型：article
- 语言：en
- 来源：ACM Transactions on Embedded Computing Systems
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1539-9087
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1145/3603171
- OpenAlex ID：https://openalex.org/W4378830682
- 落地页：https://doi.org/10.1145/3603171
- 开放 PDF 链接：https://dl.acm.org/doi/pdf/10.1145/3603171
- 主主题：Neural Networks and Applications
- 主题：Neural Networks and Applications, Advanced Neural Network Applications, Machine Learning and Data Classification
- 关键词：Computer science, Artificial intelligence, Machine learning, Robustness (evolution), Microcontroller, Process (computing), Artificial neural network, Context (archaeology), Symbolic execution, Computer engineering, Embedded system, Programming language, Software
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Machine learning at the extreme edge has enabled a plethora of intelligent, time-critical, and remote applications. However, deploying interpretable artificial intelligence systems that can perform high-level symbolic reasoning and satisfy the underlying system rules and physics within the tight platform resource constraints is challenging. In this paper, we introduce TinyNS, the first platform-aware neurosymbolic architecture search framework for joint optimization of symbolic and neural operators. TinyNS provides recipes and parsers to automatically write microcontroller code for five types of neurosymbolic models, combining the context awareness and integrity of symbolic techniques with the robustness and performance of machine learning models. TinyNS uses a fast, gradient-free, black-box Bayesian optimizer over discontinuous, conditional, numeric, and categorical search spaces to find the best synergy of symbolic code and neural networks within the hardware resource budget. To guarantee deployability, TinyNS talks to the target hardware during the optimization process. We showcase the utility of TinyNS by deploying microcontroller-class neurosymbolic models through several case studies. In all use cases, TinyNS outperforms purely neural or purely symbolic approaches while guaranteeing execution on real hardware.

## 16944. Impact of Mixed Precision Techniques on Training and Inference Efficiency of Deep Neural Networks

- 标题：Impact of Mixed Precision Techniques on Training and Inference Efficiency of Deep Neural Networks
- 作者：Marion Dörrich, Mingcheng Fan, Andreas M. Kist
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2023.3284388
- OpenAlex ID：https://openalex.org/W4379930100
- 落地页：https://doi.org/10.1109/access.2023.3284388
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/10005208/10146255.pdf
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Machine Learning in Materials Science, Machine Learning and Data Classification
- 关键词：Computer science, Deep learning, Inference, Artificial intelligence, Efficient energy use, Speedup, Machine learning, Energy consumption, Artificial neural network, Enhanced Data Rates for GSM Evolution, Excavator, Parallel computing
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In the deep learning community, increasingly large models are being developed, leading to rapidly growing computational costs and energy costs. Recently, a new trend has been arising, advocating that researchers should also report the energy efficiency besides their model’s performance in their papers. Previous research has shown that reduced precision can be helpful to improve energy efficiency. Based on this finding, we propose a simple practice to effectively improve the energy efficiency of training and inference, i.e., training the model with mixed precision and deploying it on Edge TPUs. We evaluated its effectiveness by comparing the speed-up of a state-of-the-art semantic segmentation architecture with respect to different typical usage scenarios, including using different devices, deep learning frameworks, model sizes, and batch sizes. Our results show that enabled mixed precision can gain up to a <inline-formula xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink"> <tex-math notation="LaTeX">$1.9\times $ </tex-math></inline-formula> speedup compared to the most common and default float32 data type on GPUs. Deploying the models on Edge TPU further boosted the inference by a factor of 6. Our approach allows researchers to accelerate their training and inference procedures without jeopardizing the model’s accuracy, meanwhile reducing energy consumption and electricity cost easily without changing their model architecture or retraining. Furthermore, our approach is helpful in reducing the carbon footprint used to train and deploy the neural network and thus has a positive effect on environmental resources.

## 16945. Hierarchical Decision-Making Framework for Multiple UCAVs Autonomous Confrontation

- 标题：Hierarchical Decision-Making Framework for Multiple UCAVs Autonomous Confrontation
- 作者：Yueqi Hou, Xiaolong Liang, Jiaqiang Zhang, Maolong Lv, Aiwu Yang
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Vehicular Technology
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：0018-9545
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tvt.2023.3285223
- OpenAlex ID：https://openalex.org/W4380520220
- 落地页：https://doi.org/10.1109/tvt.2023.3285223
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Robotic Path Planning Algorithms, Guidance and Control Systems
- 关键词：Interpretability, Computer science, Scalability, Event (particle physics), Software deployment, Generalization, Visualization, Action (physics), Artificial intelligence, Machine learning, Distributed computing, Software engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Autonomous decision-making for air confrontation between unmanned combat aerial vehicles remains hard to be designed due to dynamic situations and complex interactions. Rule-based decision-making methods provide a powerful solution with better interpretability. However, various hand-crafted rules may result in conflicts and poor scalability issues. To overcome this problem, this work proposes a hierarchical decision-making framework called State-Event-Condition-Action (SECA), which integrates the finite state machine and event-condition-action frameworks. This framework provides three products for system design: the SECA model–an abstract model of rules; the SECA state chart–a graphical visualization of rules; and the SECA rule description–a machine-readable format for practical deployment. The SECA framework offers several advantages, including convenient deployment, high efficiency, better logicality, and scalability. Simulation results demonstrate that the SECA framework enables autonomous decision-making in air confrontation scenarios and outperforms the event-condition-action framework in terms of computational time and cost-effectiveness. Furthermore, the generalization test in robot navigation tasks verifies its potential applicability to other domains with different background knowledge.

## 16946. RICH: A rapid method for image-text cross-modal hash retrieval

- 标题：RICH: A rapid method for image-text cross-modal hash retrieval
- 作者：Bo Li, Dan Yao, Zhixin Li
- 年份：2023
- 出版日期：2023-07-06
- 类型：article
- 语言：en
- 来源：Displays
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0141-9382
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.displa.2023.102489
- OpenAlex ID：https://openalex.org/W4383347183
- 落地页：https://doi.org/10.1016/j.displa.2023.102489
- 主主题：Advanced Image and Video Retrieval Techniques
- 主题：Advanced Image and Video Retrieval Techniques, Multimodal Machine Learning Applications, Video Analysis and Summarization
- 关键词：Computer science, Hash function, Modal, Overfitting, Artificial intelligence, Pattern recognition (psychology), Similarity (geometry), Feature (linguistics), Image retrieval, Stability (learning theory), Image (mathematics), Data mining, Machine learning, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16947. Toward domain adaptation with open-set target data: Review of theory and computer vision applications

- 标题：Toward domain adaptation with open-set target data: Review of theory and computer vision applications
- 作者：Reyhane Ghaffari, Mohammad Sadegh Helfroush, Abbas Khosravi, Kamran Kazemi, Habibollah Danyali, Leszek Rutkowski
- 年份：2023
- 出版日期：2023-07-08
- 类型：article
- 语言：en
- 来源：Information Fusion
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1566-2535
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.inffus.2023.101912
- OpenAlex ID：https://openalex.org/W4383620041
- 落地页：https://doi.org/10.1016/j.inffus.2023.101912
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Machine Learning and ELM
- 关键词：Computer science, Categorization, Domain (mathematical analysis), Domain adaptation, Set (abstract data type), Adaptation (eye), Listing (finance), Bridge (graph theory), Transfer of learning, Data set, Artificial intelligence, Point (geometry), Data mining, Machine learning, Data science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16948. Prediction of Student’s Performance With Learning Coefficients Using Regression Based Machine Learning Models

- 标题：Prediction of Student’s Performance With Learning Coefficients Using Regression Based Machine Learning Models
- 作者：Pallavi Asthana, Sumita Mishra, Nishu Gupta, Mohammad Derawi, Anil Kumar
- 年份：2023
- 出版日期：2023-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2023.3294700
- OpenAlex ID：https://openalex.org/W4384080264
- 落地页：https://doi.org/10.1109/access.2023.3294700
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/6514899/10179912.pdf
- 主主题：Online Learning and Analytics
- 主题：Online Learning and Analytics, Intelligent Tutoring Systems and Adaptive Learning, Machine Learning and Data Classification
- 关键词：Computer science, Machine learning, Artificial intelligence, Regression analysis, Regression, Linear regression, Statistics, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Advanced machine learning (ML) methods can predict student’s performance with key features based on academic, behavioral, and demographic data. Significant works have predicted the student’s performance based on the primary and secondary data sets derived from the student’s existing data. These works have accurately predicted student’s performance but did not provide the metrics as suggestions for improved performance. This paper proposes the ‘Learning Coefficients’ evaluated through trajectory-based computerized adaptive assessment. Learning coefficients also provide quantified metrics to the students to focus more on their studies and improve their further performance. Before selecting the learning coefficients as the key features for student’s performance prediction, their dependency on other key features is calculated through positive Pearson’s coefficient correlation. Further, the paper presents comparative analysis of the performance of regression-based ML models such as decision trees, random forest, support vector regression, linear regression and artificial neural networks on the same dataset. Results show that linear regression obtained the highest accuracy of 97% when compared to other models.

## 16949. MMT: Cross Domain Few-Shot Learning via Meta-Memory Transfer

- 标题：MMT: Cross Domain Few-Shot Learning via Meta-Memory Transfer
- 作者：Wenjian Wang, Lijuan Duan, Yuxi Wang, Junsong Fan, Zhaoxiang Zhang
- 年份：2023
- 出版日期：2023-08-18
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Pattern Analysis and Machine Intelligence
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：0162-8828
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tpami.2023.3306352
- OpenAlex ID：https://openalex.org/W4385976118
- 落地页：https://doi.org/10.1109/tpami.2023.3306352
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Cancer-related molecular mechanisms research
- 关键词：Computer science, Domain (mathematical analysis), Artificial intelligence, Pascal (unit), Classifier (UML), Shot (pellet), Notation, Natural language processing, Transfer of learning, Machine learning, Mathematics, Arithmetic, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
, FSS-1000, and SUIM datasets and positively affects few-shot classification tasks on Meta-Dataset.

## 16950. Work like a doctor: Unifying scan localizer and dynamic generator for automated computed tomography report generation

- 标题：Work like a doctor: Unifying scan localizer and dynamic generator for automated computed tomography report generation
- 作者：Yuhao Tang, Haichen Yang, Liyan Zhang, Ye Yuan
- 年份：2023
- 出版日期：2023-09-07
- 类型：article
- 语言：en
- 来源：Expert Systems with Applications
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0957-4174
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.eswa.2023.121442
- OpenAlex ID：https://openalex.org/W4386498861
- 落地页：https://doi.org/10.1016/j.eswa.2023.121442
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Topic Modeling, Radiomics and Machine Learning in Medical Imaging
- 关键词：Computer science, Generator (circuit theory), Artificial intelligence, Computed tomography, Task (project management), Pattern recognition (psychology), Computer vision, Radiology, Medicine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16951. Towards better Chinese-centric neural machine translation for low-resource languages

- 标题：Towards better Chinese-centric neural machine translation for low-resource languages
- 作者：Bin Li, Yixuan Weng, Fei Xia, Hanjun Deng
- 年份：2023
- 出版日期：2023-09-11
- 类型：article
- 语言：en
- 来源：Computer Speech & Language
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0885-2308
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.csl.2023.101566
- OpenAlex ID：https://openalex.org/W4386600757
- 落地页：https://doi.org/10.1016/j.csl.2023.101566
- 主主题：Natural Language Processing Techniques
- 主题：Natural Language Processing Techniques, Topic Modeling, Multimodal Machine Learning Applications
- 关键词：Computer science, Machine translation, Resource (disambiguation), Bilingual dictionary, Artificial intelligence, Competition (biology), Focus (optics), Natural language processing, World Wide Web
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16952. Explainable Enhanced Recurrent Neural Network for lie detection using voice stress analysis

- 标题：Explainable Enhanced Recurrent Neural Network for lie detection using voice stress analysis
- 作者：Fatma M. Talaat
- 年份：2023
- 出版日期：2023-09-20
- 类型：article
- 语言：en
- 来源：Multimedia Tools and Applications
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：1380-7501
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s11042-023-16769-w
- OpenAlex ID：https://openalex.org/W4386896476
- 落地页：https://doi.org/10.1007/s11042-023-16769-w
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s11042-023-16769-w.pdf
- 主主题：Deception detection and forensic psychology
- 主题：Deception detection and forensic psychology, Anomaly Detection Techniques and Applications, Adversarial Robustness in Machine Learning
- 关键词：Lie detection, Computer science, Artificial intelligence, Nonverbal communication, Artificial neural network, Speech recognition, Task (project management), Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Lie detection is a crucial aspect of human interactions that affects everyone in their daily lives. Individuals often rely on various cues, such as verbal and nonverbal communication, particularly facial expressions, to determine if someone is truthful. While automated lie detection systems can assist in identifying these cues, current approaches are limited due to a lack of suitable datasets for testing their performance in real-world scenarios. Despite ongoing research efforts to develop effective and reliable lie detection methods, this remains a work in progress. The polygraph, voice stress analysis, and pupil dilation analysis are some of the methods currently used for this task. In this study, we propose a new detection algorithm based on an Enhanced Recurrent Neural Network (ERNN) with Explainable AI capabilities. The ERNN, based on long short-term memory (LSTM) architecture, was optimized using fuzzy logic to determine the hyperparameters. The LSTM model was then created and trained using a dataset of audio recordings from interviews with a randomly selected group. The proposed ERNN achieved an accuracy of 97.3%, which is statistically significant for the problem of voice stress analysis. These results suggest that it is possible to detect patterns in the voices of individuals experiencing stress in an explainable manner.

## 16953. Effect of Feature Selection on the Accuracy of Machine Learning Model

- 标题：Effect of Feature Selection on the Accuracy of Machine Learning Model
- 作者：Asst. Professor Mohammad Salim Hamdard, Asst. Professor Hedayatullah Lodin
- 年份：2023
- 出版日期：2023-09-29
- 类型：article
- 语言：en
- 来源：INTERNATIONAL JOURNAL OF MULTIDISCIPLINARY RESEARCH AND ANALYSIS
- 来源类型：journal
- ISSN-L：2643-9840
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.47191/ijmra/v6-i9-66
- OpenAlex ID：https://openalex.org/W4387164728
- 落地页：https://doi.org/10.47191/ijmra/v6-i9-66
- 开放 PDF 链接：https://www.ijmra.in/v6i9/Doc/66.pdf
- 主主题：Face and Expression Recognition
- 主题：Face and Expression Recognition, Neural Networks and Applications, Machine Learning and Data Classification
- 关键词：Feature selection, Artificial intelligence, Machine learning, Computer science, Feature (linguistics), Perceptron, Process (computing), Selection (genetic algorithm), Decision tree, Model selection, Data mining, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In real life data science problems, it’s almost rare that all the features in the dataset are useful for building a model. In machine learning, feature selection is the process of selecting a subset of relevant features or attributes for constructing a model. Removing irrelevant and redundant features and, selecting relevant features will improve the accuracy of a machine learning model. Furthermore, adding unnecessary variables to a model increases the overall complexity of the model. Our experiment indicates that the accuracy of a classification model is highly affected by the process of feature selection. We train three algorithms (K-Nearest Neighbors, Decision Tree, Multi-layer Perceptron) by selecting all the features and we got accuracies 49%, 84% and 71% accordingly. After doing some feature selection without any logical changes in models code the accuracy scores jumped to 82%, 86% and 78% accordingly which is quite impressive.

## 16954. Self-supervised Multimodal Graph Convolutional Network for collaborative filtering

- 标题：Self-supervised Multimodal Graph Convolutional Network for collaborative filtering
- 作者：Sungjune Kim, Sungjune Kim, Seongjun Yun, Jongwuk Lee, Gyusam Chang, Wonseok Roh, Dae-Neung Sohn, Jung‐Tae Lee, Hogun Park, Sangpil Kim, Sangpil Kim
- 年份：2023
- 出版日期：2023-10-05
- 类型：article
- 语言：en
- 来源：Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0255
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ins.2023.119760
- OpenAlex ID：https://openalex.org/W4387379288
- 落地页：https://doi.org/10.1016/j.ins.2023.119760
- 主主题：Recommender Systems and Techniques
- 主题：Recommender Systems and Techniques, Human Mobility and Location-Based Analysis, Multimodal Machine Learning Applications
- 关键词：Computer science, Artificial intelligence, Robustness (evolution), Machine learning, Modalities, Graph, Benchmark (surveying), Recommender system, Collaborative filtering, Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16955. Generating collective counterfactual explanations in score-based classification via mathematical optimization

- 标题：Generating collective counterfactual explanations in score-based classification via mathematical optimization
- 作者：Emilio Carrizosa, Jasone Ramírez-Ayerbe, Dolores Romero Morales
- 年份：2023
- 出版日期：2023-10-13
- 类型：article
- 语言：en
- 来源：Expert Systems with Applications
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0957-4174
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1016/j.eswa.2023.121954
- OpenAlex ID：https://openalex.org/W4387611139
- 落地页：https://doi.org/10.1016/j.eswa.2023.121954
- 主主题：Explainable Artificial Intelligence (XAI)
- 主题：Explainable Artificial Intelligence (XAI), Machine Learning and Data Classification, Bayesian Modeling and Causal Inference
- 关键词：Counterfactual thinking, Computer science, Artificial intelligence, Machine learning, Mathematical optimization, Mathematics, Psychology, Social psychology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16956. ADMET property prediction via multi-task graph learning under adaptive auxiliary task selection

- 标题：ADMET property prediction via multi-task graph learning under adaptive auxiliary task selection
- 作者：Bing-Xue Du, Yi Xu, Siu‐Ming Yiu, Hui Yu, Jian‐Yu Shi
- 年份：2023
- 出版日期：2023-10-24
- 类型：article
- 语言：en
- 来源：iScience
- 来源类型：journal
- 出版方：Cell Press
- ISSN-L：2589-0042
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1016/j.isci.2023.108285
- OpenAlex ID：https://openalex.org/W4387910532
- 落地页：https://doi.org/10.1016/j.isci.2023.108285
- 开放 PDF 链接：https://doi.org/10.1016/j.isci.2023.108285
- 主主题：Advanced Graph Neural Networks
- 主题：Advanced Graph Neural Networks, Machine Learning and Data Classification, Machine Learning and Algorithms
- 关键词：Computer science, Task (project management), Drug discovery, Graph, Selection (genetic algorithm), Machine learning, Artificial intelligence, Property (philosophy), Computational biology, Theoretical computer science, Bioinformatics, Biology, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
It is a critical step in lead optimization to evaluate the absorption, distribution, metabolism, excretion, and toxicity (ADMET) properties of drug-like compounds. Classical single-task learning (STL) has effectively predicted individual ADMET endpoints with abundant labels. Conversely, multi-task learning (MTL) can predict multiple ADMET endpoints with fewer labels, but ensuring task synergy and highlighting key molecular substructures remain challenges. To tackle these issues, this work elaborates a multi-task graph learning framework for predicting multiple ADMET properties of drug-like small molecules (MTGL-ADMET) by holding a new paradigm of MTL, "one primary, multiple auxiliaries." It first adeptly combines status theory with maximum flow for auxiliary task selection. The subsequent phase introduces a primary-task-centric MTL model with integrated modules. MTGL-ADMET not only outstrips existing STL and MTL methods but also offers a transparent lens into crucial molecular substructures. It is anticipated that this work can promote lead compound finding and optimization in drug discovery.

## 16957. Radiology report generation with medical knowledge and multilevel image-report alignment: A new method and its verification

- 标题：Radiology report generation with medical knowledge and multilevel image-report alignment: A new method and its verification
- 作者：Guosheng Zhao, Zijian Zhao, Wuxian Gong, Feng Li
- 年份：2023
- 出版日期：2023-11-03
- 类型：article
- 语言：en
- 来源：Artificial Intelligence in Medicine
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0933-3657
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.artmed.2023.102714
- OpenAlex ID：https://openalex.org/W4388289870
- 落地页：https://doi.org/10.1016/j.artmed.2023.102714
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Topic Modeling, Natural Language Processing Techniques
- 关键词：Computer science, Closed captioning, Workload, Modalities, Medical imaging, Artificial intelligence, Image (mathematics), Data mining, Machine learning
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16958. Enhancing Algorithm Selection through Comprehensive Performance Evaluation: Statistical Analysis of Stochastic Algorithms

- 标题：Enhancing Algorithm Selection through Comprehensive Performance Evaluation: Statistical Analysis of Stochastic Algorithms
- 作者：Azad Arif Hama Amin, Aso M. Aladdin, Dler O. Hasan, Soran R. Mohammed-Taha, Tarik A. Rashid
- 年份：2023
- 出版日期：2023-11-16
- 类型：article
- 语言：en
- 来源：Computation
- 来源类型：journal
- 出版方：Multidisciplinary Digital Publishing Institute
- ISSN-L：2079-3197
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.3390/computation11110231
- OpenAlex ID：https://openalex.org/W4388729821
- 落地页：https://doi.org/10.3390/computation11110231
- 开放 PDF 链接：https://www.mdpi.com/2079-3197/11/11/231/pdf?version=1700134247
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Machine Learning and Data Classification, Data Stream Mining Techniques
- 关键词：Algorithm, Computer science, Statistical hypothesis testing, Nonparametric statistics, Selection (genetic algorithm), Wilcoxon signed-rank test, Rank (graph theory), Reliability (semiconductor), Statistical model, Ranking (information retrieval), Factor (programming language), Machine learning, Mathematics, Statistics, Mann–Whitney U test
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Analyzing stochastic algorithms for comprehensive performance and comparison across diverse contexts is essential. By evaluating and adjusting algorithm effectiveness across a wide spectrum of test functions, including both classical benchmarks and CEC-C06 2019 conference functions, distinct patterns of performance emerge. In specific situations, underscoring the importance of choosing algorithms contextually. Additionally, researchers have encountered a critical issue by employing a statistical model randomly to determine significance values without conducting other studies to select a specific model for evaluating performance outcomes. To address this concern, this study employs rigorous statistical testing to underscore substantial performance variations between pairs of algorithms, thereby emphasizing the pivotal role of statistical significance in comparative analysis. It also yields valuable insights into the suitability of algorithms for various optimization challenges, providing professionals with information to make informed decisions. This is achieved by pinpointing algorithm pairs with favorable statistical distributions, facilitating practical algorithm selection. The study encompasses multiple nonparametric statistical hypothesis models, such as the Wilcoxon rank-sum test, single-factor analysis, and two-factor ANOVA tests. This thorough evaluation enhances our grasp of algorithm performance across various evaluation criteria. Notably, the research addresses discrepancies in previous statistical test findings in algorithm comparisons, enhancing result reliability in the later research. The results proved that there are differences in significance results, as seen in examples like Leo versus the FDO, the DA versus the WOA, and so on. It highlights the need to tailor test models to specific scenarios, as p-value outcomes differ among various tests within the same algorithm pair.

## 16959. Adversarial Safety-Critical Scenario Generation Using Naturalistic Human Driving Priors

- 标题：Adversarial Safety-Critical Scenario Generation Using Naturalistic Human Driving Priors
- 作者：Kunkun Hao, Wen Cui, Yonggang Luo, Lecheng Xie, Yuqiao Bai, Jucheng Yang, Songyang Yan, Yuxi Pan, Zijiang Yang
- 年份：2023
- 出版日期：2023-11-23
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Intelligent Vehicles
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2379-8858
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tiv.2023.3335862
- OpenAlex ID：https://openalex.org/W4388936562
- 落地页：https://doi.org/10.1109/tiv.2023.3335862
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Autonomous Vehicle Technology and Safety, Robotic Path Planning Algorithms
- 关键词：Prior probability, Adversarial system, Computer science, Artificial intelligence, Bayesian probability
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Evaluating the decision-making system is indispensable in developing autonomous vehicles, while realistic and challenging safety-critical test scenarios play a crucial role. Obtaining these scenarios is non-trivial, thanks to the long-tailed distribution, sparsity, and rarity in real-world data sets. To tackle this problem, in this paper, we introduce a natural adversarial scenario generation solution using naturalistic human driving priors and reinforcement learning techniques. By doing this, we can obtain large-scale test scenarios that are both diverse and realistic. Specifically, we build a simulation environment that mimics natural traffic interaction scenarios. Informed by this environment, we implement a two-stage procedure. The first stage incorporates conventional rule-based models, e.g., IDM (Intelligent Driver Model) and MOBIL (Minimizing Overall Braking Induced by Lane changes) model, to coarsely and discretely capture and calibrate key control parameters from the real-world dataset. Next, we leverage GAIL (Generative Adversarial Imitation Learning) to represent driver behaviors continuously. The derived GAIL can be further used to design a PPO (Proximal Policy Optimization)-based actor-critic network framework to fine-tune the reward function, and then optimize our natural adversarial scenario generation solution. Extensive experiments have been conducted in two popular datasets, NGSIM and INTERACTION. Essential traffic parameters were measured in comparison with the baseline model, e.g., the collision rate, accelerations, steering, and the number of lane changes. Our findings demonstrate that the proposed model can generate realistic safety-critical test scenarios covering both naturalness and adversariality with an advanced 44% efficiency gain over the baseline model, which can be a cornerstone for the development of autonomous vehicles.

## 16960. Robust and Secure Federated Learning Against Hybrid Attacks: A Generic Architecture

- 标题：Robust and Secure Federated Learning Against Hybrid Attacks: A Generic Architecture
- 作者：Xiaohan Hao, Chao Lin, Wenhan Dong, Xinyi Huang, Hui Xiong
- 年份：2023
- 出版日期：2023-11-23
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Forensics and Security
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1556-6013
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tifs.2023.3336521
- OpenAlex ID：https://openalex.org/W4388938021
- 落地页：https://doi.org/10.1109/tifs.2023.3336521
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Cryptography and Data Security, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Computer security, Client-side, Plaintext, Server, Scalability, Composability, Robustness (evolution), Server-side, Architecture, Threat model, Cryptography, Ciphertext, Encryption, Distributed computing, Software deployment, Computer network, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Federated Learning (FL) enables multiple clients to collaboratively train a model without sharing their private data. However, the deployment of FL in real-world applications is vulnerable to various attacks from both malicious servers and clients. While cryptographic methods are effective in resisting server-side attacks, they undermine the capability of client-side defenses that rely on plaintext updates. Several valuable defenses targeting hybrid attacks have been devised to address this challenge, concentrating on specific client-side threats. To improve scalability, we continue this research line to introduce a generic architecture covering more client-side attacks. In this paper, we propose a general architecture to enhance client-side defenses from plaintext to ciphertext domains. This architecture not only supports the server-side defenses, but also accommodates a broader range of client-side defenses, including Norm-based, Krum-based, and Cosine-based strategies. The core of our architecture is generic detection under ciphertext, which tackles the following conflict of integrating server-side and client-side defenses. That is, the former aims to protect parameters from exposure while the latter demands plaintext updates. We prove the security of our architecture through the Universal Composability framework. Additionally, we provide a comprehensive instantiation and extensive evaluations to demonstrate the effectiveness and robustness of our approach. Our experiments show that our architecture can maintain the effectiveness of current client-side defenses when parameters are encrypted, thus effectively resisting hybrid attacks.

## 16961. SIR-Aided Secure Transmission and Attack Detection for Security Management of Nonlinear Cyber-Physical System Using GRU Autoencoder

- 标题：SIR-Aided Secure Transmission and Attack Detection for Security Management of Nonlinear Cyber-Physical System Using GRU Autoencoder
- 作者：Shimeng Wu, Hao Luo, Yuchen Jiang, Jiusi Zhang, Jilun Tian, Shen Yin
- 年份：2023
- 出版日期：2023-12-05
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Industrial Informatics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1551-3203
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tii.2023.3331546
- OpenAlex ID：https://openalex.org/W4389331434
- 落地页：https://doi.org/10.1109/tii.2023.3331546
- 主主题：Smart Grid Security and Resilience
- 主题：Smart Grid Security and Resilience, Advanced Malware Detection Techniques, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Encryption, Autoencoder, Transmission (telecommunications), Plaintext, Cryptography, Artificial intelligence, Data mining, Unsupervised learning, Computer engineering, Computer security, Artificial neural network
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This article designs a data-driven unsupervised defense scheme for nonlinear systems by proposing a machine learning approach called gate recurrent unit-based modified denoising and stable image representation-aided autoencoders. The proposed scheme decomposes original data into two subspaces through orthogonal projection. For secure transmission, information related to the system's dynamics, which is in the image space of the controlled system, is hidden through filtering, whereas only the dynamic-independent information is plaintext for transmission, which supplements the cryptographic encryption methods from a control perspective. Moreover, attack detection for nonstealthy and stealthy attacks is achieved simultaneously under the same framework. A case study is conducted for validation on the a hardware-in-the-loop platform with a mecanum-wheeled vehicle. The comparative experiments with well-known unsupervised data-driven methods show the high detection accuracy of the proposed defense scheme for nonstealthy and stealthy attacks and the excellent encryption capability.

## 16962. Improved binary differential evolution with dimensionality reduction mechanism and binary stochastic search for feature selection

- 标题：Improved binary differential evolution with dimensionality reduction mechanism and binary stochastic search for feature selection
- 作者：Behrouz Ahadzadeh, Moloud Abdar, Fatemeh Safara, Leyla Aghaei, Seyedali Mirjalili, Abbas Khosravi, Salvador García, Fakhri Karray, U. Rajendra Acharya
- 年份：2023
- 出版日期：2023-12-13
- 类型：article
- 语言：en
- 来源：Applied Soft Computing
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1568-4946
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.asoc.2023.111141
- OpenAlex ID：https://openalex.org/W4389671032
- 落地页：https://doi.org/10.1016/j.asoc.2023.111141
- 主主题：Metaheuristic Optimization Algorithms Research
- 主题：Metaheuristic Optimization Algorithms Research, Evolutionary Algorithms and Applications, Machine Learning and Data Classification
- 关键词：Computer science, Dimensionality reduction, Feature selection, Binary number, Support vector machine, Classifier (UML), Curse of dimensionality, Binary classification, Artificial intelligence, Pattern recognition (psychology), Local optimum, Differential evolution, Feature vector, Machine learning, Data mining, Algorithm, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Computer systems store massive amounts of data with numerous features, leading to the need to extract the most important features for better classification in a wide variety of applications. Poor performance of various machine learning algorithms may be caused by unimportant features that increase the time and memory required to build a classifier. Feature selection (FS) is one of the efficient approaches to reducing the unimportant features. This paper, therefore, presents a new FS, named BDE-BSS-DR, that utilizes Binary Differential Evolution (BDE), Binary Stochastic Search (BSS) algorithm, and Dimensionality Reduction (DR) mechanism. The BSS algorithm increases the search capability of the BDE by escaping from local optimal points and exploring the search space. The DR mechanism then reduces the dimensions of the search space gradually. As a result of using DR, the local optima of the search space and the problem of wrong removal of important features before starting the search process are reduced. The algorithm's efficiency is evaluated on 20 different medical datasets. The obtained outcomes indicate that the BDE-BSS-DR outperforms the BDE and BDE-BSS algorithms significantly. Furthermore, the effectiveness of the proposed algorithms in selecting the most important features of the heart disease data, several cancer diseases, and COVID-19 are also compared with several other state-of-the-art methods. Our results show that the BDE-BSS-DR with SVM classifier has a significant advantage over other methods with an average classification accuracy of 95.05% in heart disease and 99.40% in COVID-19 disease. In addition, the comparisons made with KNN and SVM classification prove the efficiency of the DR and BSS in generating a subset of optimal and informative features.

## 16963. Revisiting Confidence Estimation: Towards Reliable Failure Prediction

- 标题：Revisiting Confidence Estimation: Towards Reliable Failure Prediction
- 作者：Fei Zhu, Xu-Yao Zhang, Zhen Cheng, Cheng‐Lin Liu
- 年份：2023
- 出版日期：2023-12-13
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Pattern Analysis and Machine Intelligence
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：0162-8828
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tpami.2023.3342285
- OpenAlex ID：https://openalex.org/W4389692358
- 落地页：https://doi.org/10.1109/tpami.2023.3342285
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Adversarial Robustness in Machine Learning, Machine Learning and Data Classification
- 关键词：Calibration, Computer science, Bridge (graph theory), Confidence interval, Artificial intelligence, Machine learning, Covariate, Baseline (sea), Estimation, Data mining, Statistics, Mathematics, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Reliable confidence estimation is a challenging yet fundamental requirement in many risk-sensitive applications. However, modern deep neural networks are often overconfident for their incorrect predictions, <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">i.e.</i> , misclassified samples from known classes, and out-of-distribution (OOD) samples from unknown classes. In recent years, many confidence calibration and OOD detection methods have been developed. In this paper, we find a general, widely existing but actually-neglected phenomenon that most confidence estimation methods are harmful for detecting misclassification errors. We investigate this problem and reveal that popular calibration and OOD detection methods often lead to worse confidence separation between correctly classified and misclassified examples, making it difficult to decide whether to trust a prediction or not. Finally, we propose to enlarge the confidence gap by finding flat minima, which yields state-of-the-art failure prediction performance under various settings including balanced, long-tailed, and covariate-shift classification scenarios. Our study not only provides a strong baseline for reliable confidence estimation but also acts as a bridge between understanding calibration, OOD detection, and failure prediction.

## 16964. Instruction-ViT: Multi-modal prompts for instruction learning in vision transformer

- 标题：Instruction-ViT: Multi-modal prompts for instruction learning in vision transformer
- 作者：Zhenxiang Xiao, Yuzhong Chen, Junjie Yao, Lu Zhang, Zhengliang Liu, Zihao Wu, Xiaowei Yu, Yi Pan, Lin Zhao, Chong Ma, Xinyu Liu, Wei Liu
- 年份：2023
- 出版日期：2023-12-18
- 类型：article
- 语言：en
- 来源：Information Fusion
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1566-2535
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.inffus.2023.102204
- OpenAlex ID：https://openalex.org/W4389903841
- 落地页：https://doi.org/10.1016/j.inffus.2023.102204
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning, Natural Language Processing Techniques
- 关键词：Computer science, Adaptability, Closed captioning, Transformer, Modal, Artificial intelligence, Scalability, Human–computer interaction, Machine learning, Natural language processing, Image (mathematics), Voltage
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16965. Sensor fault diagnosis and correction for data center cooling system using hybrid multi-label random Forest and Bayesian Inference

- 标题：Sensor fault diagnosis and correction for data center cooling system using hybrid multi-label random Forest and Bayesian Inference
- 作者：Jiaqiang Wang, Yaoyue Tian, Zhaohui Qi, Liping Zeng, Peng Wang, Sungmin Yoon
- 年份：2023
- 出版日期：2023-12-18
- 类型：article
- 语言：en
- 来源：Building and Environment
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0360-1323
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.buildenv.2023.111124
- OpenAlex ID：https://openalex.org/W4389955411
- 落地页：https://doi.org/10.1016/j.buildenv.2023.111124
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Machine Learning and Data Classification, Data Stream Mining Techniques
- 关键词：Computer science, Random forest, Medical diagnosis, Fault (geology), Bayesian probability, Fault detection and isolation, Inference, Bayesian inference, Real-time computing, Data mining, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16966. S3-Net: A Self-Supervised Dual-Stream Network for Radiology Report Generation

- 标题：S3-Net: A Self-Supervised Dual-Stream Network for Radiology Report Generation
- 作者：Renjie Pan, Ruisheng Ran, Wei Hu, Wenfeng Zhang, Qibing Qin, Shaoguo Cui
- 年份：2023
- 出版日期：2023-12-22
- 类型：article
- 语言：en
- 来源：IEEE Journal of Biomedical and Health Informatics
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2168-2194
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/jbhi.2023.3345932
- OpenAlex ID：https://openalex.org/W4390120105
- 落地页：https://doi.org/10.1109/jbhi.2023.3345932
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Topic Modeling, Natural Language Processing Techniques
- 关键词：Computer science, Artificial intelligence, Feature (linguistics), Encoder, Feature learning, Fuse (electrical), Deep learning, Pattern recognition (psychology), Exploit, Representation (politics), Machine learning, Computer vision
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Intelligent medicine is eager to automatically generate radiology reports to ease the tedious work of radiologists. Previous researches mainly focused on the text generation with encoder-decoder structure, while CNN networks for visual features ignored the long-range dependencies correlated with textual information. Besides, few studies exploit cross-modal mappings to promote radiology report generation. To alleviate the above problems, we propose a novel end-to-end radiology report generation model dubbed Self-Supervised dual-Stream Network (S3-Net). Specifically, a Dual-Stream Visual Feature Extractor (DSVFE) composed of ResNet and SwinTransformer is proposed to capture more abundant and effective visual features, where the former focuses on local response and the latter explores long-range dependencies. Then, we introduced the Fusion Alignment Module (FAM) to fuse the dual-stream visual features and facilitate alignment between visual features and text features. Furthermore, the Self-Supervised Learning with Mask(SSLM) is introduced to further enhance the visual feature representation ability. Experimental results on two mainstream radiology reporting datasets (IU X-ray and MIMIC-CXR) show that our proposed approach outperforms previous models in terms of language generation metrics.

## 16967. Variational Distillation for Multi-View Learning

- 标题：Variational Distillation for Multi-View Learning
- 作者：Xudong Tian, Zhizhong Zhang, Cong Wang, Wensheng Zhang, Yanyun Qu, Lizhuang Ma, Zongze Wu, Yuan Xie, Dacheng Tao
- 年份：2023
- 出版日期：2023-12-22
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Pattern Analysis and Machine Intelligence
- 来源类型：journal
- 出版方：IEEE Computer Society
- ISSN-L：0162-8828
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tpami.2023.3343717
- OpenAlex ID：https://openalex.org/W4390120148
- 落地页：https://doi.org/10.1109/tpami.2023.3343717
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Advanced Neural Network Applications, Adversarial Robustness in Machine Learning
- 关键词：Information bottleneck method, Consistency (knowledge bases), Distillation, Mutual information, Computer science, Representation (politics), Artificial intelligence, Viewpoints, Key (lock), Bottleneck, Machine learning, Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
D tackles the difficulties in MI optimization and fully realizes the theoretical advantages of the information bottleneck principle. We extensively evaluate our model on diverse tasks to verify its effectiveness, where the considerable gains provide key insights into achieving generalized multi-view representations under a rigorous information-theoretic principle.

## 16968. Bayesian DivideMix++ for Enhanced Learning with Noisy Labels

- 标题：Bayesian DivideMix++ for Enhanced Learning with Noisy Labels
- 作者：Bhalaji Nagarajan, Ricardo Marques, Eduardo Aguilar, Petia Radeva
- 年份：2024
- 出版日期：2024-01-10
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.neunet.2024.106122
- OpenAlex ID：https://openalex.org/W4390707243
- 落地页：https://doi.org/10.1016/j.neunet.2024.106122
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Machine Learning and Algorithms, Advanced Neural Network Applications
- 关键词：Computer science, Artificial intelligence, Machine learning, Robustness (evolution), Pipeline (software), Deep learning, Artificial neural network, Deep neural networks, Noise (video), Bayesian probability, Generalization, Crawling
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Leveraging inexpensive and human intervention-based annotating methodologies, such as crowdsourcing and web crawling, often leads to datasets with noisy labels. Noisy labels can have a detrimental impact on the performance and generalization of deep neural networks. Robust models that are able to handle and mitigate the effect of these noisy labels are thus essential. In this work, we explore the open challenges of neural network memorization and uncertainty in creating robust learning algorithms with noisy labels. To overcome them, we propose a novel framework called "Bayesian DivideMix++" with two critical components: (i) DivideMix++, to enhance the robustness against memorization and (ii) Monte-Carlo MixMatch, which focuses on improving the effectiveness towards label uncertainty. DivideMix++ improves the pipeline by integrating the warm-up and augmentation pipeline with self-supervised pre-training and dedicated different data augmentations for loss analysis and backpropagation. Monte-Carlo MixMatch leverages uncertainty measurements to mitigate the influence of uncertain samples by reducing their weight in the data augmentation MixMatch step. We validate our proposed pipeline using four datasets encompassing various synthetic and real-world noise settings. We demonstrate the effectiveness and merits of our proposed pipeline using extensive experiments. Bayesian DivideMix++ outperforms the state-of-the-art models by considerable differences in all experiments. Our findings underscore the potential of leveraging these modifications to enhance the performance and generalization of deep neural networks in practical scenarios.

## 16969. View-Invariant Skeleton Action Representation Learning via Motion Retargeting

- 标题：View-Invariant Skeleton Action Representation Learning via Motion Retargeting
- 作者：Di Yang, Yaohui Wang, Antitza Dantcheva, Lorenzo Garattoni, Gianpiero Francesca, François Brémond
- 年份：2024
- 出版日期：2024-01-16
- 类型：article
- 语言：en
- 来源：International Journal of Computer Vision
- 来源类型：journal
- 出版方：Springer Science+Business Media
- ISSN-L：0920-5691
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1007/s11263-023-01967-8
- OpenAlex ID：https://openalex.org/W4390906058
- 落地页：https://doi.org/10.1007/s11263-023-01967-8
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Gait Recognition and Analysis, Multimodal Machine Learning Applications
- 关键词：Artificial intelligence, Computer science, Retargeting, Autoencoder, Invariant (physics), Representation (politics), Computer vision, Feature learning, Skeleton (computer programming), RGB color model, Action recognition, Viewpoints, Pattern recognition (psychology), Deep learning, Mathematics, Class (philosophy)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16970. Similarity-Based Label Inference Attack Against Training and Inference of Split Learning

- 标题：Similarity-Based Label Inference Attack Against Training and Inference of Split Learning
- 作者：Junlin Liu, Xinchen Lyu, Qimei Cui, Xiaofeng Tao
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Forensics and Security
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1556-6013
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tifs.2024.3356821
- OpenAlex ID：https://openalex.org/W4391093146
- 落地页：https://doi.org/10.1109/tifs.2024.3356821
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning
- 关键词：Computer science, Inference, Artificial intelligence, Similarity (geometry), Machine learning, Training set, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Split learning is a promising paradigm for privacy-preserving distributed learning. The learning model can be cut into multiple portions to be collaboratively trained at the participants by exchanging only the intermediate results at the cut layer. Understanding the security performance of split learning is critical for many privacy-sensitive applications. This paper shows that the exchanged intermediate results, including the smashed data (i.e., extracted features from the raw data) and gradients during training and inference of split learning, can already reveal the private labels. We mathematically analyze the potential label leakages and propose the cosine and Euclidean similarity measurements for gradients and smashed data, respectively. Then, the two similarity measurements are shown to be unified in Euclidean space. Based on the similarity metric, we design three label inference attacks to efficiently recover the private labels during both the training and inference phases. Experimental results validate that the proposed approaches can achieve close to 100% accuracy of label attacks. The proposed attack can still achieve accurate predictions against various state-of-the-art defense mechanisms, including DP-SGD, label differential privacy, gradient compression, and Marvell.

## 16971. Constraining Adversarial Attacks on Network Intrusion Detection Systems: Transferability and Defense Analysis

- 标题：Constraining Adversarial Attacks on Network Intrusion Detection Systems: Transferability and Defense Analysis
- 作者：Nour Alhussien, Ahmed Aleroud, Abdullah Melhem, Samer Khamaiseh
- 年份：2024
- 出版日期：2024-01-22
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Network and Service Management
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1932-4537
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tnsm.2024.3357316
- OpenAlex ID：https://openalex.org/W4391097056
- 落地页：https://doi.org/10.1109/tnsm.2024.3357316
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Anomaly Detection Techniques and Applications, Network Security and Intrusion Detection
- 关键词：Adversarial system, Computer science, Transferability, Artificial intelligence, Machine learning, Robustness (evolution), Intrusion detection system, Feature (linguistics), Support vector machine, Deep learning, Data mining
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Adversarial attacks have been extensively studied in the domain of deep image classification, but their impacts on other domains such as Machine and Deep Learning-based Network Intrusion Detection Systems (NIDSs) have received limited attention. While adversarial attacks on images are generally more straightforward due to fewer constraints in the input domain, generating adversarial examples in the network domain poses greater challenges due to the diverse types of network traffic and the need to maintain its validity. Prior research has introduced constraints to generate adversarial examples against NIDSs, but their effectiveness across different attack settings, including transferability, targetability, defenses, and the overall attack success have not been thoroughly examined. In this paper, we proposed a novel set of domain constraints for network traffic that preserve the statistical and semantic relationships between traffic features while ensuring the validity of the perturbed adversarial traffic. Our constraints are categorized into four types: feature mutability constraints, feature value constraints, feature dependency constraints and distribution preserving constraints. We evaluated the impacts of these constraints on white box and black box attacks using two intrusion detection datasets. Our results demonstrated that the introduced constraints have a significant impact on the success of white box attacks. Our research revealed that transferability of adversarial examples depends on the similarity between the targeted models and the models to which the examples are transferred, regardless of the attack type or the presence of constraints. We also observed that adversarial training enhanced the robustness of the majority of machine learning and deep learning-based NIDSs against unconstrained attacks, while providing some resilience against constrained attacks. In practice, this suggests the potential use of pre-existing signatures of constrained attacks to combat new variations or zero-day adversarial attacks in real-world NIDSs.

## 16972. Improving transferability of 3D adversarial attacks with scale and shear transformations

- 标题：Improving transferability of 3D adversarial attacks with scale and shear transformations
- 作者：Jinlai Zhang, Yinpeng Dong, Jun Zhu, Jun Zhu, Jihong Zhu, Jihong Zhu, Minchi Kuang, Xiaming Yuan
- 年份：2024
- 出版日期：2024-02-01
- 类型：article
- 语言：en
- 来源：Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0255
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.ins.2024.120245
- OpenAlex ID：https://openalex.org/W4391427688
- 落地页：https://doi.org/10.1016/j.ins.2024.120245
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, High-Velocity Impact and Material Behavior, Physical Unclonable Functions (PUFs) and Hardware Security
- 关键词：Transferability, Adversarial system, Scale (ratio), Computer science, Shear (geology), Artificial intelligence, Computer security, Data science, Data mining, Geology, Machine learning, Petrology, Geography, Cartography
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16973. Misbehavior detection in intelligent transportation systems based on federated learning

- 标题：Misbehavior detection in intelligent transportation systems based on federated learning
- 作者：Enrique Mármol Campos, José L. Hernández-Ramos, Aurora González-Vidal, Gianmarco Baldini, Antonio Skármeta
- 年份：2024
- 出版日期：2024-02-15
- 类型：article
- 语言：en
- 来源：Internet of Things
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：2542-6605
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.iot.2024.101127
- OpenAlex ID：https://openalex.org/W4391850627
- 落地页：https://doi.org/10.1016/j.iot.2024.101127
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Adversarial Robustness in Machine Learning, Imbalanced Data Classification Techniques
- 关键词：Computer science, Scalability, Machine learning, Artificial intelligence, Latency (audio), Multilayer perceptron, Context (archaeology), Key (lock), Cryptography, Computer security, Artificial neural network, Database
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Misbehavior detection represents a key security approach in vehicular scenarios to identify attacks that cannot be detected by traditional cryptographic mechanisms. In this context, the application of Machine Learning (ML) techniques has been widely considered to identify increasingly sophisticated misbehavior attacks. However, most of the proposed approaches are based on centralized settings, which could pose privacy issues, as well as an increased latency leading to severe consequences in the vehicular environment where real-time and scalability requirements are challenging. To address this issue, we propose a collaborative learning approach based on Federated Learning (FL) for vehicles’ misbehavior detection. We use the reference misbehavior dataset VeReMi, which is re-balanced by applying the SMOTE-Tomek technique. We carry out a thorough evaluation considering different balancing settings and number of nodes. The evaluation results overcome recent state-of-the-art approaches, with an overall accuracy of 93% using an optimized multilayer perceptron (MLP) for multiclass classification.

## 16974. Red Teaming Language Model Detectors with Language Models

- 标题：Red Teaming Language Model Detectors with Language Models
- 作者：Zhouxing Shi, Yihan Wang, Fan Yin, Xiangning Chen, Kai-Wei Chang, Cho‐Jui Hsieh
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：Transactions of the Association for Computational Linguistics
- 来源类型：journal
- 出版方：Association for Computational Linguistics
- ISSN-L：2307-387X
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：diamond
- DOI：10.1162/tacl_a_00639
- OpenAlex ID：https://openalex.org/W4391876565
- 落地页：https://doi.org/10.1162/tacl_a_00639
- 主主题：Topic Modeling
- 主题：Topic Modeling, Natural Language Processing Techniques, Multimodal Machine Learning Applications
- 关键词：Computer science, Language model, Natural language processing, Detector, Artificial intelligence, Telecommunications
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract The prevalence and strong capability of large language models (LLMs) present significant safety and ethical risks if exploited by malicious users. To prevent the potentially deceptive usage of LLMs, recent work has proposed algorithms to detect LLM-generated text and protect LLMs. In this paper, we investigate the robustness and reliability of these LLM detectors under adversarial attacks. We study two types of attack strategies: 1) replacing certain words in an LLM’s output with their synonyms given the context; 2) automatically searching for an instructional prompt to alter the writing style of the generation. In both strategies, we leverage an auxiliary LLM to generate the word replacements or the instructional prompt. Different from previous works, we consider a challenging setting where the auxiliary LLM can also be protected by a detector. Experiments reveal that our attacks effectively compromise the performance of all detectors in the study with plausible generations, underscoring the urgent need to improve the robustness of LLM-generated text detection systems. Code is available at https://github.com/shizhouxing/LLM-Detector-Robustness.

## 16975. Addressing Bias in Machine Learning Algorithms: Promoting Fairness and Ethical Design

- 标题：Addressing Bias in Machine Learning Algorithms: Promoting Fairness and Ethical Design
- 作者：Dharmesh Dhabliya, Sukhvinder Singh Dari, Anishkumar Dhablia, N. Akhila, Renu Kachhoria, Vinit Khetani
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：E3S Web of Conferences
- 来源类型：journal
- 出版方：EDP Sciences
- ISSN-L：2267-1242
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：diamond
- DOI：10.1051/e3sconf/202449102040
- OpenAlex ID：https://openalex.org/W4391998543
- 落地页：https://doi.org/10.1051/e3sconf/202449102040
- 开放 PDF 链接：https://www.e3s-conferences.org/articles/e3sconf/pdf/2024/21/e3sconf_icecs2024_02040.pdf
- 主主题：Ethics and Social Impacts of AI
- 主题：Ethics and Social Impacts of AI, Explainable Artificial Intelligence (XAI), Adversarial Robustness in Machine Learning
- 关键词：Computer science, Artificial intelligence, Machine learning, Psychology
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Machine learning algorithms have quickly risen to the top of several fields' decision-making processes in recent years. However, it is simple for these algorithms to confirm already present prejudices in data, leading to biassed and unfair choices. In this work, we examine bias in machine learning in great detail and offer strategies for promoting fair and moral algorithm design. The paper then emphasises the value of fairnessaware machine learning algorithms, which aim to lessen bias by including fairness constraints into the training and evaluation procedures. Reweighting, adversarial training, and resampling are a few strategies that could be used to overcome prejudice. Machine learning systems that better serve society and respect ethical ideals can be developed by promoting justice, transparency, and inclusivity. This paper lays the groundwork for researchers, practitioners, and policymakers to forward the cause of ethical and fair machine learning through concerted effort.

## 16976. RVE-PFL: Robust Variational Encoder-Based Personalized Federated Learning Against Model Inversion Attacks

- 标题：RVE-PFL: Robust Variational Encoder-Based Personalized Federated Learning Against Model Inversion Attacks
- 作者：Wael Issa, Nour Moustafa, Benjamin Turnbull, Kim‐Kwang Raymond Choo
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Information Forensics and Security
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1556-6013
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tifs.2024.3368879
- OpenAlex ID：https://openalex.org/W4392024995
- 落地页：https://doi.org/10.1109/tifs.2024.3368879
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Adversarial Robustness in Machine Learning, Cryptography and Data Security
- 关键词：Computer science, Encoder, Federated learning, Inversion (geology), Artificial intelligence, Distributed computing, Operating system
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Federated learning (FL) enables distributed joint training of machine learning (ML) models without the need to share local data. FL is, however, not immune to privacy threats such as model inversion (MI) attacks. The conventional FL paradigm often uses privacy-preserving techniques, and this could lead to a considerable loss in the model’s utility and consequently compromised by MI attackers. Seeking to address this limitation, this paper proposes a robust variational encoder-based personalised FL (RVE-PFL) approach that mitigates MI attacks, preserves model utility, and ensures data privacy. RVE-PFL comprises an innovative personalised variational encoder architecture and a trustworthy threat model-integrated FL method to autonomously preserve data privacy, and mitigate MI attacks. The proposed architecture seamlessly trains heterogeneous data at every client, while the proposed approach aggregates data at the server side and effectively discriminates against adversarial settings (i.e., MI); thus, achieving robustness and trustworthiness in real-time. RVE-PFL is evaluated on three benchmark datasets, namely: MNIST, Fashion-MNIST, and Cifar-10. The experimental results revealed that RVE-PFL achieves high accuracy level while preserving data and tuning adversarial settings. It outperforms Noising before Model Aggregation FL (NbAFL) with significant accuracy improvements of 8%, 20%, and 59% on MNIST, Fashion-MNIST, and Cifar-10, respectively. These findings reinforce the effectiveness of RVE-PFL in protecting against MI attacks while maintaining the model’s utility. The source code for RVE-PFL can be found on GitHub 1.

## 16977. The role of trust in the use of artificial intelligence for chemical risk assessment

- 标题：The role of trust in the use of artificial intelligence for chemical risk assessment
- 作者：Pim N.H. Wassenaar, Jordi Minnema, Jelle Vriend, Willie J.G.M. Peijnenburg, Jeroen L. A. Pennings, Anne S. Kienhuis
- 年份：2024
- 出版日期：2024-02-23
- 类型：article
- 语言：en
- 来源：Regulatory Toxicology and Pharmacology
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0273-2300
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.yrtph.2024.105589
- OpenAlex ID：https://openalex.org/W4392112443
- 落地页：https://doi.org/10.1016/j.yrtph.2024.105589
- 主主题：Risk and Safety Analysis
- 主题：Risk and Safety Analysis, Occupational Health and Safety Research, Adversarial Robustness in Machine Learning
- 关键词：Risk assessment, Risk analysis (engineering), Business, Computer science, Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16978. Learning to Preselection: A Filter-Based Performance Predictor for Multiobjective Feature Selection in Classification

- 标题：Learning to Preselection: A Filter-Based Performance Predictor for Multiobjective Feature Selection in Classification
- 作者：Ruwang Jiao, Bing Xue, Mengjie Zhang
- 年份：2024
- 出版日期：2024-03-06
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Evolutionary Computation
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1089-778X
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tevc.2024.3373802
- OpenAlex ID：https://openalex.org/W4392523547
- 落地页：https://doi.org/10.1109/tevc.2024.3373802
- 主主题：Machine Learning and Data Classification
- 主题：Machine Learning and Data Classification, Face and Expression Recognition, Neural Networks and Applications
- 关键词：Artificial intelligence, Feature selection, Selection (genetic algorithm), Computer science, Filter (signal processing), Machine learning, Multi-objective optimization, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Minimizing the classification error rate and the number of selected features are the two major objectives of feature selection, and they are often in conflict with each other, which is a multiobjective problem. Evolutionary algorithms have been widely used for multiobjective feature selection problems. Preselection in evolutionary algorithms is used to improve the sampling quality by selecting only potentially promising candidate solutions for fitness evaluations. However, traditional preselection methods struggle to effectively handle feature selection due to its large-scale combinatorial nature and intricate feature interactions. To alleviate this issue, this paper proposes a filter-based performance predictor to preselect feature subsets for subsequent classification fitness evaluations. It uses multiple filter measures to estimate the classification performance of a feature subset, which can explore complex feature interactions and is also insensitive to the dimensionality. Additionally, a correlation coefficient is used to measure the compatibility between the learned performance predictor and the classification performance. Based on the degree of compatibility, a preselection method that considers both the predicted classification performance and the feature subset diversity is proposed, which can preselect promising solutions from multiple candidate solutions and thus improve the feature subset search efficiency. The proposed method is verified experimentally on a total of 18 classification datasets spanning various domains, and the results reveal that it can find feature subsets with better classification performance and converge faster to competitive results compared to state-of-the-art methods.

## 16979. COFT-AD: COntrastive Fine-Tuning for Few-Shot Anomaly Detection

- 标题：COFT-AD: COntrastive Fine-Tuning for Few-Shot Anomaly Detection
- 作者：Jingyi Liao, Xun Xu, Manh Cuong Nguyen, Adam Goodge, Chuan-Sheng Foo
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tip.2024.3374048
- OpenAlex ID：https://openalex.org/W4392693636
- 落地页：https://doi.org/10.1109/tip.2024.3374048
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Radiation Detection and Scintillator Technologies, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Anomaly detection, Artificial intelligence, Pattern recognition (psychology), Computer vision
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Existing approaches towards anomaly detection (AD) often rely on a substantial amount of anomaly-free data to train representation and density models. However, large anomaly-free datasets may not always be available before the inference stage; in which case an anomaly detection model must be trained with only a handful of normal samples, a.k.a. few-shot anomaly detection (FSAD). In this paper, we propose a novel methodology to address the challenge of FSAD which incorporates two important techniques. Firstly, we employ a model pre-trained on a large source dataset to initialize model weights. Secondly, to ameliorate the covariate shift between source and target domains, we adopt contrastive training to fine-tune on the few-shot target domain data. To learn suitable representations for the downstream AD task, we additionally incorporate cross-instance positive pairs to encourage a tight cluster of the normal samples, and negative pairs for better separation between normal and synthesized negative samples. We evaluate few-shot anomaly detection on 3 controlled AD tasks and 4 real-world AD tasks to demonstrate the effectiveness of the proposed method.

## 16980. DPFLA: Defending Private Federated Learning Against Poisoning Attacks

- 标题：DPFLA: Defending Private Federated Learning Against Poisoning Attacks
- 作者：Xia Feng, Wenhao Cheng, Chunjie Cao, Liangmin Wang, Victor S. Sheng
- 年份：2024
- 出版日期：2024-03-12
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Services Computing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1939-1374
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tsc.2024.3376255
- OpenAlex ID：https://openalex.org/W4392719441
- 落地页：https://doi.org/10.1109/tsc.2024.3376255
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Cryptography and Data Security, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Computer security, Computer network, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Federated learning (FL) is vulnerable to data poisoning attacks when an adversary attempts to upload poison gradients with the intent to corrupt the global model of FL. Various approaches have been proposed to counter these risks. However, it becomes challenging when one tries to preserve the privacy of FL participants and ensure robustness against data poisoning attacks. In this paper, we propose DPFLA, a novel scheme that can detect poisoning attacks without revealing the actual gradients of participants. DPFLA is a lossless aggregation scheme delicately designed for adopting masks to protect private data while extracting poisoned data features. Specifically, we first apply removable masks to the gradients outputted by each participant. Second, we aggregate the masked data and decompose them using Singular Value Decomposition (SVD) to extract specific features as well as achieve dimensionality reduction. Third, we leverage a clustering paradigm to detect poison gradients from the low dimension and eliminate them in the following training rounds. We conducted extensive experiments to demonstrate that DPFLA can detect poison gradients effectively. Additionally, the comparisons of case studies demonstrate that DPFLA outperforms the state-of-the-art methods.

## 16981. Federated Active Learning (F-AL): An Efficient Annotation Strategy for Federated Learning

- 标题：Federated Active Learning (F-AL): An Efficient Annotation Strategy for Federated Learning
- 作者：Jin-Hyun Ahn, Yeeun Ma, Seoyun Park, Cheolwoo You
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2024.3376746
- OpenAlex ID：https://openalex.org/W4392745656
- 落地页：https://doi.org/10.1109/access.2024.3376746
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/10380310/10471526.pdf
- 主主题：Machine Learning and Algorithms
- 主题：Machine Learning and Algorithms, Cryptography and Data Security, Privacy-Preserving Technologies in Data
- 关键词：Computer science, Annotation, Active learning (machine learning), Federated learning, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Federated learning (FL) has been intensively investigated in terms of communication efficiency, privacy, and fairness. However, efficient annotation, which is a pain point in real-world FL applications, is less studied. In this project, we propose to apply active learning (AL) to the FL framework to reduce the annotation workload. We expect that the AL and FL can improve the performance of each other complementarily. In our proposed federated active learning (F-AL) method, the clients collaboratively execute the AL to obtain the instances which are considered informative to FL in a distributed optimization manner. We compare the test accuracies of the global FL models using the conventional random sampling strategy, client-level separate AL (S-AL), and the proposed F-AL. We empirically demonstrate that the F-AL outperforms baseline methods in image classification tasks.

## 16982. Adaptive tree-like neural network: Overcoming catastrophic forgetting to classify streaming data with concept drifts

- 标题：Adaptive tree-like neural network: Overcoming catastrophic forgetting to classify streaming data with concept drifts
- 作者：Yimin Wen, Xiang Liu, Hang Yu
- 年份：2024
- 出版日期：2024-03-16
- 类型：article
- 语言：en
- 来源：Knowledge-Based Systems
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0950-7051
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.knosys.2024.111636
- OpenAlex ID：https://openalex.org/W4392883826
- 落地页：https://doi.org/10.1016/j.knosys.2024.111636
- 主主题：Data Stream Mining Techniques
- 主题：Data Stream Mining Techniques, Machine Learning and Data Classification, Advanced Bandit Algorithms Research
- 关键词：Forgetting, Computer science, Tree (set theory), Artificial neural network, Artificial intelligence, Set (abstract data type), Code (set theory), Adaptability, Position (finance), Node (physics), Machine learning, Data mining, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16983. An evolutionary neural architecture search method based on performance prediction and weight inheritance

- 标题：An evolutionary neural architecture search method based on performance prediction and weight inheritance
- 作者：Gonglin Yuan, Bing Xue, Mengjie Zhang
- 年份：2024
- 出版日期：2024-03-20
- 类型：article
- 语言：en
- 来源：Information Sciences
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0020-0255
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1016/j.ins.2024.120466
- OpenAlex ID：https://openalex.org/W4392983060
- 落地页：https://doi.org/10.1016/j.ins.2024.120466
- 主主题：Anomaly Detection Techniques and Applications
- 主题：Anomaly Detection Techniques and Applications, Machine Learning and Data Classification, Neural Networks and Applications
- 关键词：Inheritance (genetic algorithm), Computer science, Artificial neural network, Genetic architecture, Artificial intelligence, Architecture, Evolutionary algorithm, Machine learning, Biology, Quantitative trait locus, Genetics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Evolutionary Neural Architecture Search (ENAS) algorithms attract great attention since they can automatically search for appropriate network architectures for a given task. However, most ENAS algorithms suffer from a prohibitive computational burden. Moreover, some of these approaches directly use performance predictors for evaluations, which may introduce inaccurate assessments and harm the evolution. To overcome these shortcomings, we propose an efficient ENAS algorithm named EPPGA. EPPGA employs a predictor to pre-select potentially high-performing offspring, enhancing the performance and accelerating the evolution. As the offspring will be further accurately evaluated, even potentially inaccurate predictions will not adversely affect the evolution. Furthermore, a weight inheritance method is suggested to accelerate the evaluation, and new genetic operations are developed to produce offspring that share a substantial proportion of beneficial genetic materials with one parent, improving the performance predictor's effectiveness and promoting weight inheritance. Finally, a new efficient backbone block structure is designed to facilitate the search for lightweight networks. The experimental results demonstrate that EPPGA is a highly competitive algorithm on three benchmarks in terms of accuracy, model size, and computational cost, reveal the superiority of the proposed block structure, and confirm the effectiveness of the proposed performance predictor and weight inheritance method.

## 16984. Progressively Select and Reject Pseudolabeled Samples for Open-Set Domain Adaptation

- 标题：Progressively Select and Reject Pseudolabeled Samples for Open-Set Domain Adaptation
- 作者：Qian Wang, Fanlin Meng, Toby P. Breckon
- 年份：2024
- 出版日期：2024-03-25
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Artificial Intelligence
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2691-4581
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tai.2024.3379940
- OpenAlex ID：https://openalex.org/W4393144927
- 落地页：https://doi.org/10.1109/tai.2024.3379940
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Machine Learning and ELM, Multimodal Machine Learning Applications
- 关键词：Adaptation (eye), Domain adaptation, Set (abstract data type), Open set, Computer science, Biology, Mathematics, Artificial intelligence, Combinatorics, Neuroscience, Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Domain adaptation solves image classification problems in the target domain by taking advantage of the labelled source data and unlabelled target data. Usually, the source and target domains share the same set of classes. As a special case, Open-Set Domain Adaptation (OSDA) assumes there exist additional classes in the target domain but are not present in the source domain. To solve such a domain adaptation problem, our proposed method learns discriminative common subspaces for the source and target domains using a novel Open-Set Locality Preserving Projection (OSLPP) algorithm. The source and target domain data are aligned in the learned common spaces class-wise. To handle the open-set classification problem, our method progressively selects target samples to be pseudo-labelled as known classes, rejects the outliers if they are detected as unknown classes, and leaves the remaining target samples as uncertain. The common subspace learning algorithm OSLPP simultaneously aligns the labelled source data and pseudo-labelled target data from known classes and pushes the rejected target data away from the known classes. The common subspace learning and the pseudo-labelled sample selection/rejection facilitate each other in an iterative learning framework and achieve state-of-the-art performance on four benchmark datasets Office-31, Office-Home, VisDA17 and Syn2Real-O with the average HOS of 87.6%, 67.0%, 76.1% and 65.6% respectively.

## 16985. BadCM: Invisible Backdoor Attack Against Cross-Modal Learning

- 标题：BadCM: Invisible Backdoor Attack Against Cross-Modal Learning
- 作者：Zheng Zhang, Yuan Xu, Lei Zhu, Jingkuan Song, Liqiang Nie
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Image Processing
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：1057-7149
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1109/tip.2024.3378918
- OpenAlex ID：https://openalex.org/W4393184763
- 落地页：https://doi.org/10.1109/tip.2024.3378918
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning, Rabies epidemiology and control
- 关键词：Backdoor, Modal, Computer science, Generalization, Modality (human–computer interaction), Artificial intelligence, Invariant (physics), Theoretical computer science, Machine learning, Computer security, Mathematics
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Despite remarkable successes in unimodal learning tasks, backdoor attacks against cross-modal learning are still underexplored due to the limited generalization and inferior stealthiness when involving multiple modalities. Notably, since works in this area mainly inherit ideas from unimodal visual attacks, they struggle with dealing with diverse cross-modal attack circumstances and manipulating imperceptible trigger samples, which hinders their practicability in real-world applications. In this paper, we introduce a novel bilateral backdoor to fill in the missing pieces of the puzzle in the cross-modal backdoor and propose a generalized invisible backdoor framework against cross-modal learning (BadCM). Specifically, a cross-modal mining scheme is developed to capture the modality-invariant components as target poisoning areas, where well-designed trigger patterns injected into these regions can be efficiently recognized by the victim models. This strategy is adapted to different image-text cross-modal models, making our framework available to various attack scenarios. Furthermore, for generating poisoned samples of high stealthiness, we conceive modality-specific generators for visual and linguistic modalities that facilitate hiding explicit trigger patterns in modality-invariant regions. To the best of our knowledge, BadCM is the first invisible backdoor method deliberately designed for diverse cross-modal attacks within one unified framework. Comprehensive experimental evaluations on two typical applications, i.e., cross-modal retrieval and VQA, demonstrate the effectiveness and generalization of our method under multiple kinds of attack scenarios. Moreover, we show that BadCM can robustly evade existing backdoor defenses. Our code is available at https://github.com/xandery-geek/BadCM.

## 16986. An active machine learning approach for optimal design of magnesium alloys using Bayesian optimisation

- 标题：An active machine learning approach for optimal design of magnesium alloys using Bayesian optimisation
- 作者：M. Ghorbani, Mario Boley, Philip N. H. Nakashima, N. Birbilis
- 年份：2024
- 出版日期：2024-04-09
- 类型：article
- 语言：en
- 来源：Scientific Reports
- 来源类型：journal
- 出版方：Nature Portfolio
- ISSN-L：2045-2322
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1038/s41598-024-59100-9
- OpenAlex ID：https://openalex.org/W4394620585
- 落地页：https://doi.org/10.1038/s41598-024-59100-9
- 开放 PDF 链接：https://www.nature.com/articles/s41598-024-59100-9.pdf
- 主主题：Machine Learning in Materials Science
- 主题：Machine Learning in Materials Science, Machine Learning and Algorithms, Metal and Thin Film Mechanics
- 关键词：Bayesian optimization, Regret, Computer science, Workflow, Gaussian process, Probabilistic logic, Machine learning, Process (computing), Bayesian probability, Kriging, Graphical user interface, Artificial intelligence, Data mining, Gaussian, Database
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In the pursuit of magnesium (Mg) alloys with targeted mechanical properties, a multi-objective Bayesian optimisation workflow is presented to enable optimal Mg-alloy design. A probabilistic Gaussian process regressor model was trained through an active learning loop, while balancing the exploration and exploitation trade-off via an acquisition function of the upper confidence bound. New candidate alloys suggested by the optimiser within each iteration were appended to the training data, and the performance of this sequential strategy was validated via a regret analysis. Using the proposed approach, the dependency of the prediction error on the training data was overcome by considering both the predictions and their associated uncertainties. The method developed here, has been packaged into a web tool with a graphical user-interactive interface (GUI) that allows the proposed optimal Mg-alloy design strategy to be deployed.

## 16987. Three Challenges to Secure AI Systems in the Context of AI Regulations

- 标题：Three Challenges to Secure AI Systems in the Context of AI Regulations
- 作者：Ronan Hamon, H. Junklewitz, Josep Soler Garrido, Ignacio Sánchez
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2024.3391021
- OpenAlex ID：https://openalex.org/W4394994574
- 落地页：https://doi.org/10.1109/access.2024.3391021
- 开放 PDF 链接：https://ieeexplore.ieee.org/ielx7/6287639/6514899/10506836.pdf
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Ethics and Social Impacts of AI
- 关键词：Computer science, Context (archaeology), Computer security
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
This article examines the interplay between artificial intelligence (AI) and cybersecurity in light of future regulatory requirements on the security of AI systems, specifically focusing on the robustness of high-risk AI systems against cyberattacks in the context of the European Union’s AI Act. The paper identifies and analyses three challenges to achieve compliance of AI systems with the cybersecurity requirement: accounting for the diversity and the complexity of AI technologies, assessing AI-specific risks, and developing secure-by-design AI systems. The contribution of the article consists in providing an overview of AI cybersecurity practices and identifying gaps in current approaches to security conformity assessment for AI systems. Our analysis highlights the unique vulnerabilities present in AI systems and the absence of established cybersecurity practices tailored to these systems, and emphasises the need for continuous alignment between legal requirements and technological capabilities, acknowledging the necessity for further research and development to address the challenges. It concludes that comprehensive cybersecurity practices must evolve to accommodate the unique aspects of AI, with a collaborative effort from various sectors to ensure effective implementation and standardisation.

## 16988. A Survey of Multimodal Perception Methods for Human–Robot Interaction in Social Environments

- 标题：A Survey of Multimodal Perception Methods for Human–Robot Interaction in Social Environments
- 作者：John A. Duncan, Farshid Alambeigi, Mitch Pryor
- 年份：2024
- 出版日期：2024-04-29
- 类型：article
- 语言：en
- 来源：ACM Transactions on Human-Robot Interaction
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：2573-9522
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1145/3657030
- OpenAlex ID：https://openalex.org/W4396230859
- 落地页：https://doi.org/10.1145/3657030
- 开放 PDF 链接：https://dl.acm.org/doi/pdf/10.1145/3657030
- 主主题：Human Pose and Action Recognition
- 主题：Human Pose and Action Recognition, Multimodal Machine Learning Applications, Social Robot Interaction and HRI
- 关键词：Human–robot interaction, Human–computer interaction, Perception, Computer science, Social robot, Robot, Psychology, Cognitive psychology, Artificial intelligence, Mobile robot, Robot control, Neuroscience
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Human–robot interaction (HRI) in human social environments (HSEs) poses unique challenges for robot perception systems, which must combine asynchronous, heterogeneous data streams in real time. Multimodal perception systems are well-suited for HRI in HSEs and can provide more rich, robust interaction for robots operating among humans. In this article, we provide an overview of multimodal perception systems being used in HSEs, which is intended to be an introduction to the topic and summary of relevant trends, techniques, resources, challenges, and terminology. We surveyed 15 peer-reviewed robotics and HRI publications over the past 10+ years, providing details about the data acquisition, processing, and fusion techniques used in 65 multimodal perception systems across various HRI domains. Our survey provides information about hardware, software, datasets, and methods currently available for HRI perception research, as well as how these perception systems are being applied in HSEs. Based on the survey, we summarize trends, challenges, and limitations of multimodal human perception systems for robots, then identify resources for researchers and developers and propose future research areas to advance the field.

## 16989. Control With Style: Style Embedding-Based Variational Autoencoder for Controlled Stylized Caption Generation Framework

- 标题：Control With Style: Style Embedding-Based Variational Autoencoder for Controlled Stylized Caption Generation Framework
- 作者：Dhruv Sharma, Chhavi Dhiman, Dinesh Kumar
- 年份：2024
- 出版日期：2024-05-30
- 类型：article
- 语言：en
- 来源：IEEE Transactions on Cognitive and Developmental Systems
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2379-8920
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1109/tcds.2024.3405573
- OpenAlex ID：https://openalex.org/W4399168182
- 落地页：https://doi.org/10.1109/tcds.2024.3405573
- 主主题：Video Analysis and Summarization
- 主题：Video Analysis and Summarization, Multimodal Machine Learning Applications, Subtitles and Audiovisual Media
- 关键词：Stylized fact, Autoencoder, Computer science, Style (visual arts), Embedding, Control (management), Artificial intelligence, Speech recognition, Artificial neural network, Art
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Automatic Image captioning is a computationally intensive and structurally complicated task that describes the contents of an image in the form of a natural language sentence. Methods developed in the recent past focused mainly on the description of factual content in images thereby ignoring the different emotions and styles (romantic, humorous, angry, etc.) associated with the image. To overcome this, few works incorporated style-based caption generation that captures the variability in the generated descriptions. This paper presents a Style Embedding-based Variational Autoencoder for Controlled Stylized Caption Generation Framework (RFCG+SE-VAE-CSCG). It generates controlled text-based stylized descriptions of images. It works in two phases i.e., ( <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">i</i> ) Refined Factual Caption Generation (RFCG), and ( <italic xmlns:mml="http://www.w3.org/1998/Math/MathML" xmlns:xlink="http://www.w3.org/1999/xlink">ii</i> ) SE-VAE-CSCG. The former defines an encoder-decoder model for the generation of refined factual captions. Whereas, the latter presents a style embedding-based variational autoencoder for controlled stylized caption generation. The overall proposed framework generates style-based descriptions of images by leveraging Bag-of-Captions (BoC). More so, with the use of a controlled text generation model, the proposed work efficiently learns disentangled representations and generates realistic stylized descriptions of images. Experiments on MSCOCO, Flickr30K, and FlickrStyle10K provide state-of-the-art results for both refined and style-based caption generation, supported with an ablation study.

## 16990. Prototype learning for adversarial domain adaptation

- 标题：Prototype learning for adversarial domain adaptation
- 作者：Yuchun Fang, Chen Chen, Wei Zhang, Jiahua Wu, Zhaoxiang Zhang, Shaorong Xie
- 年份：2024
- 出版日期：2024-06-05
- 类型：article
- 语言：en
- 来源：Pattern Recognition
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0031-3203
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.patcog.2024.110653
- OpenAlex ID：https://openalex.org/W4399357582
- 落地页：https://doi.org/10.1016/j.patcog.2024.110653
- 主主题：Domain Adaptation and Few-Shot Learning
- 主题：Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications, Viral Infections and Vectors
- 关键词：Discriminative model, Computer science, Adversarial system, Domain adaptation, Artificial intelligence, Domain (mathematical analysis), Representation (politics), Feature learning, Machine learning, Invariant (physics), Adaptation (eye), Feature (linguistics), Pattern recognition (psychology), Mathematics, Classifier (UML)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16991. Hydra: Multi-head low-rank adaptation for parameter efficient fine-tuning

- 标题：Hydra: Multi-head low-rank adaptation for parameter efficient fine-tuning
- 作者：Sanghyeon Kim, Hyun-Mo Yang, Yunghyun Kim, Youngjoon Hong, Eunbyung Park
- 年份：2024
- 出版日期：2024-06-07
- 类型：article
- 语言：en
- 来源：Neural Networks
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：0893-6080
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.neunet.2024.106414
- OpenAlex ID：https://openalex.org/W4399422592
- 落地页：https://doi.org/10.1016/j.neunet.2024.106414
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Domain Adaptation and Few-Shot Learning, Multimodal Machine Learning Applications
- 关键词：Computer science, Lernaean Hydra, Inference, Adaptation (eye), Generalization, Fine-tuning, Artificial intelligence, Machine learning, Theoretical computer science
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

## 16992. Docimological Quality Analysis of LLM-Generated Multiple Choice Questions in Computer Science and Medicine

- 标题：Docimological Quality Analysis of LLM-Generated Multiple Choice Questions in Computer Science and Medicine
- 作者：Christian Grévisse, Maria Angeliki S. Pavlou, Jochen G. Schneider
- 年份：2024
- 出版日期：2024-06-10
- 类型：article
- 语言：en
- 来源：SN Computer Science
- 来源类型：journal
- 出版方：Springer Nature
- ISSN-L：2661-8907
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1007/s42979-024-02963-6
- OpenAlex ID：https://openalex.org/W4399487593
- 落地页：https://doi.org/10.1007/s42979-024-02963-6
- 开放 PDF 链接：https://link.springer.com/content/pdf/10.1007/s42979-024-02963-6.pdf
- 主主题：Topic Modeling
- 主题：Topic Modeling, Natural Language Processing Techniques, Multimodal Machine Learning Applications
- 关键词：Multiple choice, Computer science, Quality (philosophy), Plug-in, Generative grammar, Task (project management), Transformer, Artificial intelligence, Medicine
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Abstract Assessment is an essential part of education, both for teachers who assess their students as well as learners who may evaluate themselves. Multiple-choice questions (MCQ) are one of the most popular types of knowledge assessment, e.g., in medical education, as they can be automatically graded and can cover a wide range of learning items. However, the creation of high-quality MCQ items is a time-consuming task. The recent advent of Large Language Models (LLM), such as Generative Pre-trained Transformer (GPT), caused a new momentum for automatic question generation solutions. Still, evaluating generated questions according to the best practices for MCQ item writing is needed to ensure docimological quality. In this article, we propose an analysis of the quality of LLM-generated MCQs. We employ zero-shot approaches in two domains, namely computer science and medicine. In the former, we make use of 3 GPT-based services to generate MCQs. In the latter, we developed a plugin for the Moodle learning management system that generates MCQs based on learning material. We compare the generated MCQs against common multiple-choice item writing guidelines. Among the major challenges, we determined that while LLMs are certainly useful in generating MCQs more efficiently, they sometimes create broad items with ambiguous keys or implausible distractors. Human oversight is also necessary to ensure instructional alignment between generated items and course contents. Finally, we propose solutions for AQG developers.

## 16993. Rethinking Deep CNN Training: A Novel Approach for Quality-Aware Dataset Optimization

- 标题：Rethinking Deep CNN Training: A Novel Approach for Quality-Aware Dataset Optimization
- 作者：Bohdan Rusyn, Oleksiy Lutsyk, Rostyslav Kosarevych, Oleg Kapshii, Oleksandr Karpin, Taras Maksymyuk, Juraj Gazda
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2024.3414651
- OpenAlex ID：https://openalex.org/W4399665963
- 落地页：https://doi.org/10.1109/access.2024.3414651
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Anomaly Detection Techniques and Applications, Machine Learning and Data Classification
- 关键词：Computer science, Artificial intelligence, Training (meteorology), Quality (philosophy), Machine learning, Pattern recognition (psychology)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The informativeness of data has always been of great interest within the machine learning community. Nowadays, with the skyrocketing advancement of artificial intelligence and massive volumes of noisy data, it becomes even more essential to develop robust and effective methods for training data optimization. Existing approaches are mostly based on empirical trial and error, with either stochastic or deterministic data reduction strategies. The key limitation of such solutions is that they do not consider the overall informativeness of the resulting training dataset. In this paper, a novel approach for quality-aware dataset optimization by initial assessment of its informativeness is proposed. As a metric of informativeness, entropy values are calculated over the target dataset. To alleviate the computational complexity, an initial clustering of the dataset is performed, and the entropy of each cluster is calculated independently. The dataset is then optimized by dynamic programming to find a sequence of subsets with low overall entropy according to imposed size limitations. The experimental evaluation shows that the proposed approach improves over current best alternatives in terms of accuracy, precision, recall, and F1-score metrics. Moreover, the proposed approach provides excellent interclass discrimination even for a large number of classes.

## 16994. Trojan Attack and Defense for Deep Learning-Based Navigation Systems of Unmanned Aerial Vehicles

- 标题：Trojan Attack and Defense for Deep Learning-Based Navigation Systems of Unmanned Aerial Vehicles
- 作者：Mohammed Mynuddin, Sultan Uddin Khan, Reza Ahmari, Luis Landivar, Mahmoud Nabil, Abdollah Homaifar
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2024.3419800
- OpenAlex ID：https://openalex.org/W4400072132
- 落地页：https://doi.org/10.1109/access.2024.3419800
- 主主题：Adversarial Robustness in Machine Learning
- 主题：Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques, Advanced Neural Network Applications
- 关键词：Trojan, Computer science, Robustness (evolution), Computer security, Vulnerability (computing), Threat model, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
As unmanned aerial vehicles (UAVs) become increasingly integrated across various domains, both military and civilian, safeguarding the security of their navigation systems becomes paramount. In the contemporary age, the prominence of cybersecurity for UAVs has grown due to a rising number of cyberattacks on these systems. Notably, over the past decade, several significant cybersecurity breaches have impacted UAVs due to inadequate vulnerability assessments and security measures. Deep learning (DL)-based algorithms show immense potential for enabling autonomous UAV navigation. However, these algorithms are susceptible to malicious attacks, such as DL-based Trojan attacks, which can compromise the integrity and reliability of UAV navigation systems. This paper addresses potential vulnerabilities in DL-based UAV navigation systems and emphasizes the importance of securing these systems against DL-based Trojan attacks. We design various trigger patterns for collision and steering angle of the DroNet model incorporating adversarial inputs to test the robustness of the deep learning algorithm used for UAV navigation. By simulating potential attacks and studying their effects, we aim to highlight the weaknesses and potential entry points for malicious interference. We assess the effectiveness of Trojan attacks on the DroNet model using poisoned collision and steering angle datasets. Subsequently, we regulate the intensity of the designed triggers and evaluate the performance of the DroNet architecture. Additionally, we propose mitigation strategies to enhance the robustness and security of navigation systems against these attacks. To identify the likelihood of the trained model being trojaned or not, we have developed a Trojan detector and created distinct DroNet Trojan Model Datasets for this purpose. That the DroNet model is vulnerable to DL-based Trojan attacks, as evidenced by the successful manipulation of collision and steering angle predictions. The Trojan detector effectively identifies potential compromises within the model, highlighting the necessity for enhanced security measures.

## 16995. A Lightweight and Secure Deep Learning Model for Privacy-Preserving Federated Learning in Intelligent Enterprises

- 标题：A Lightweight and Secure Deep Learning Model for Privacy-Preserving Federated Learning in Intelligent Enterprises
- 作者：Reza Fotohi, Fereidoon Shams Aliee, Bahar Farahani
- 年份：2024
- 出版日期：2024-07-01
- 类型：article
- 语言：en
- 来源：IEEE Internet of Things Journal
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2327-4662
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1109/jiot.2024.3421602
- OpenAlex ID：https://openalex.org/W4400188335
- 落地页：https://doi.org/10.1109/jiot.2024.3421602
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Stochastic Gradient Optimization Techniques, Adversarial Robustness in Machine Learning
- 关键词：Computer science, Computer security, Deep learning, Information privacy, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
The ever-growing Internet of Things (IoT) connections drive a new type of organization, the intelligent enterprise. In intelligent enterprises, machine learning-based models are adopted to extract insights from data. Due to these traditional models’ efficiency and privacy challenges, a new federated learning (FL) paradigm has emerged. In FL, multiple enterprises can jointly train a model to update a final model. However, first, FL-trained models usually perform worse than centralized models, especially when enterprises’ training data are nonindependent and identically distributed (IID). Second, due to the centrality of FL and the untrustworthiness of local enterprises, traditional FL solutions are vulnerable to poisoning and inference attacks and violate privacy. Third, the continuous transfer of parameters between enterprises and servers increases communication costs. Therefore, to this end, the FedAnil+ model is proposed, a novel, lightweight, and secure Federated Deep Learning Model that includes three main phases. In the first phase, the goal is to solve the data type distribution skew challenge. Addressing privacy concerns against poisoning and inference attacks is given in the second phase. Finally, to alleviate the communication overhead, a novel compression approach is proposed that significantly reduces the size of the updates. The experiment results validate that FedAnil+ is secure against inference and poisoning attacks with better accuracy. In addition, in terms of model accuracy (13%, 16%, and 26%), communication cost (17%, 21%, and 25%), and computation cost (7%, 9%, and 11%) improvements over existing approaches. The FedAnil+ code is available on GitHub.

## 16996. <i>The first step is the hardest</i>: pitfalls of representing and tokenizing temporal data for large language models

- 标题：<i>The first step is the hardest</i>: pitfalls of representing and tokenizing temporal data for large language models
- 作者：Dimitris Spathis, Fahim Kawsar
- 年份：2024
- 出版日期：2024-07-01
- 类型：article
- 语言：en
- 来源：Journal of the American Medical Informatics Association
- 来源类型：journal
- 出版方：Oxford University Press
- ISSN-L：1067-5027
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：green
- DOI：10.1093/jamia/ocae090
- OpenAlex ID：https://openalex.org/W4400266577
- 落地页：https://doi.org/10.1093/jamia/ocae090
- 主主题：Topic Modeling
- 主题：Topic Modeling, Artificial Intelligence in Healthcare and Education, Multimodal Machine Learning Applications
- 关键词：Computer science, Natural language processing, Data science, Artificial intelligence
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
OBJECTIVES: Large language models (LLMs) have demonstrated remarkable generalization and across diverse tasks, leading individuals to increasingly use them as personal assistants due to their emerging reasoning capabilities. Nevertheless, a notable obstacle emerges when including numerical/temporal data into these prompts, such as data sourced from wearables or electronic health records. LLMs employ tokenizers in their input that break down text into smaller units. However, tokenizers are not designed to represent numerical values and might struggle to understand repetitive patterns and context, treating consecutive values as separate tokens and disregarding their temporal relationships. This article discusses the challenges of representing and tokenizing temporal data. It argues that naively passing timeseries to LLMs can be ineffective due to the modality gap between numbers and text. MATERIALS AND METHODS: We conduct a case study by tokenizing a sample mobile sensing dataset using the OpenAI tokenizer. We also review recent works that feed timeseries data into LLMs for human-centric tasks, outlining common experimental setups like zero-shot prompting and few-shot learning. RESULTS: The case study shows that popular LLMs split timestamps and sensor values into multiple nonmeaningful tokens, indicating they struggle with temporal data. We find that preliminary works rely heavily on prompt engineering and timeseries aggregation to "ground" LLMs, hinting that the "modality gap" hampers progress. The literature was critically analyzed through the lens of models optimizing for expressiveness versus parameter efficiency. On one end of the spectrum, training large domain-specific models from scratch is expressive but not parameter-efficient. On the other end, zero-shot prompting of LLMs is parameter-efficient but lacks expressiveness for temporal data. DISCUSSION: We argue tokenizers are not optimized for numerical data, while the scarcity of timeseries examples in training corpora exacerbates difficulties. We advocate balancing model expressiveness and computational efficiency when integrating temporal data. Prompt tuning, model grafting, and improved tokenizers are highlighted as promising directions. CONCLUSION: We underscore that despite promising capabilities, LLMs cannot meaningfully process temporal data unless the input representation is addressed. We argue that this paradigm shift in how we leverage pretrained models will particularly affect the area of biomedical signals, given the lack of modality-specific foundation models.

## 16997. Your Code Secret Belongs to Me: Neural Code Completion Tools Can Memorize Hard-Coded Credentials

- 标题：Your Code Secret Belongs to Me: Neural Code Completion Tools Can Memorize Hard-Coded Credentials
- 作者：Yizhan Huang, Yichen Li, Weibin Wu, Jianping Zhang, Michael R. Lyu
- 年份：2024
- 出版日期：2024-07-12
- 类型：article
- 语言：en
- 来源：Proceedings of the ACM on software engineering.
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：2994-970X
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：hybrid
- DOI：10.1145/3660818
- OpenAlex ID：https://openalex.org/W4400582422
- 落地页：https://doi.org/10.1145/3660818
- 主主题：Privacy-Preserving Technologies in Data
- 主题：Privacy-Preserving Technologies in Data, Adversarial Robustness in Machine Learning, Advanced Malware Detection Techniques
- 关键词：Computer science, Code (set theory), Memorization, Arithmetic, Programming language, Psychology, Mathematics, Cognitive psychology, Set (abstract data type)
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Neural Code Completion Tools (NCCTs) have reshaped the field of software engineering, which are built upon the language modeling technique and can accurately suggest contextually relevant code snippets. However, language models may emit the training data verbatim during inference with appropriate prompts. This memorization property raises privacy concerns of NCCTs about hard-coded credential leakage, leading to unauthorized access to applications, systems, or networks. Therefore, to answer whether NCCTs will emit the hard-coded credential, we propose an evaluation tool called H ard-coded C redential R evealer (HCR). HCR constructs test prompts based on GitHub code files with credentials to reveal the memorization phenomenon of NCCTs. Then, HCR designs four filters to filter out ill-formatted credentials. Finally, HCR directly checks the validity of a set of non-sensitive credentials. We apply HCR to evaluate three representative types of NCCTs: Commercial NCCTs, open-source models, and chatbots with code completion capability. Our experimental results show that NCCTs can not only return the precise piece of their training data but also inadvertently leak additional secret strings. Notably, two valid credentials were identified during our experiments. Therefore, HCR raises a severe privacy concern about the potential leakage of hard-coded credentials in the training data of commercial NCCTs. All artifacts and data are released for future research purposes in https://github.com/HCR-Repo/HCR .

## 16998. Utilizing YOLO Models for Real-World Scenarios: Assessing Novel Mixed Defect Detection Dataset in PCBs

- 标题：Utilizing YOLO Models for Real-World Scenarios: Assessing Novel Mixed Defect Detection Dataset in PCBs
- 作者：Vinod Kumar Ancha, Fadi N. Sibai, Venkateswarlu Gonuguntla, Ramesh Vaddi
- 年份：2024
- 出版日期：2024-01-01
- 类型：article
- 语言：en
- 来源：IEEE Access
- 来源类型：journal
- 出版方：Institute of Electrical and Electronics Engineers
- ISSN-L：2169-3536
- OpenAlex 引用数：22
- 开放获取：是
- OA 状态：gold
- DOI：10.1109/access.2024.3430329
- OpenAlex ID：https://openalex.org/W4400770913
- 落地页：https://doi.org/10.1109/access.2024.3430329
- 主主题：Advanced Neural Network Applications
- 主题：Advanced Neural Network Applications, Industrial Vision Systems and Defect Detection, Machine Learning and Data Classification
- 关键词：Computer science, Inference, Limiting, Usability, Printed circuit board, Software deployment, Artificial intelligence, Data mining, Machine learning, Engineering
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
In the domain of printed circuit board (PCB) defect detection and classification, the availability of diverse and comprehensive datasets is fundamental for developing effective detection models. However, existing datasets often lack comprehensive labeling and focus on specific defect types, limiting their applicability to real-world scenarios. To address this gap, we introduce a new dataset named ‘dataset for Mixed Defect Detection in PCB’ (MDD_PCB), which includes intentionally induced mixed PCB defects to provide a more realistic representation of practical scenarios. We evaluate the MDD_PCB dataset using YOLO models and implement it successfully for real-time inference on Jetson Nano, achieving enhanced detection capabilities. Our optimized YOLOv5n model trained on the MDD_PCB dataset achieves impressive metrics (accuracy 93%, precision 95%, recall 96%, mAP 95%, F1-score 94%) with a detection speed of 120.69 frames per second (FPS). Real-time deployment on the Jetson Nano demonstrates practical usability with a detection speed of 30 frames per second (FPS). These results underscore the significance of the diverse dataset proposed, which contributes to robust detection solutions and advances in PCB defect detection methodologies.

## 16999. Action-aware Linguistic Skeleton Optimization Network for Non-autoregressive Video Captioning

- 标题：Action-aware Linguistic Skeleton Optimization Network for Non-autoregressive Video Captioning
- 作者：Shuqin Chen, Xian Zhong, Yi Zhang, Lei Zhu, Ping Li, Xiaokang Yang, Bin Sheng
- 年份：2024
- 出版日期：2024-07-20
- 类型：article
- 语言：en
- 来源：ACM Transactions on Multimedia Computing Communications and Applications
- 来源类型：journal
- 出版方：Association for Computing Machinery
- ISSN-L：1551-6857
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1145/3679203
- OpenAlex ID：https://openalex.org/W4400850904
- 落地页：https://doi.org/10.1145/3679203
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Human Pose and Action Recognition, Video Surveillance and Tracking Methods
- 关键词：Computer science, Closed captioning, Action (physics), Skeleton (computer programming), Autoregressive model, Artificial intelligence, Human–computer interaction, Natural language processing, Speech recognition, Image (mathematics), Programming language
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full

摘要：
Non-autoregressive video captioning methods generate visual words in parallel but often overlook semantic correlations among them, especially regarding verbs, leading to lower caption quality. To address this, we integrate action information of highlighted objects to enhance semantic connections among visual words. Our proposed Action-aware Language Skeleton Optimization Network (ALSO-Net) tackles the challenge of extracting action information across frames, improving understanding of complex context-dependent video actions and reducing sentence inconsistencies. ALSO-Net incorporates a linguistic skeleton tag generator to refine semantic correlations and a video action predictor to enhance verb prediction accuracy in video captions. We also address issues of unsatisfactory caption length and quality by jointly optimizing different levels of motion prediction loss. Experimental evaluation on prominent video captioning datasets demonstrates that ALSO-Net outperforms baseline methods by a significant margin and achieves competitive performance compared to state-of-the-art autoregressive methods with smaller model complexity and faster inference time.

## 17000. Surgical-VQLA++: Adversarial contrastive learning for calibrated robust visual question-localized answering in robotic surgery

- 标题：Surgical-VQLA++: Adversarial contrastive learning for calibrated robust visual question-localized answering in robotic surgery
- 作者：Long Bai, Guankun Wang, Mobarakol Islam, Lalithkumar Seenivasan, An Wang, Hongliang Ren
- 年份：2024
- 出版日期：2024-07-27
- 类型：article
- 语言：en
- 来源：Information Fusion
- 来源类型：journal
- 出版方：Elsevier BV
- ISSN-L：1566-2535
- OpenAlex 引用数：22
- 开放获取：否
- OA 状态：closed
- DOI：10.1016/j.inffus.2024.102602
- OpenAlex ID：https://openalex.org/W4401044130
- 落地页：https://doi.org/10.1016/j.inffus.2024.102602
- 主主题：Multimodal Machine Learning Applications
- 主题：Multimodal Machine Learning Applications, Domain Adaptation and Few-Shot Learning, Robotics and Sensor-Based Localization
- 关键词：Adversarial system, Computer science, Artificial intelligence, Question answering, Computer vision, Natural language processing, Human–computer interaction
- 知识库方向：机器学习
- 方向分组：AI/计算机
- 语料类型：full
