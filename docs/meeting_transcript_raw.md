# Raw Meeting Transcript — World Model Evaluation Pipeline

**Date:** 2026-03-10

These are the raw meeting transcriptions, preserved verbatim for future reference. The meeting was transcribed in 4 segments.

---

## Segment 1 — 2026-03-10T13:27:47-07:00

Action 非常多，Modal 的 action 非常多。

然后你 eyeballing 23 个不同的 action 非常困难，或者你用一些 automatic，搞了一个什么 optical flow，那每一个数字代表什么？

23 个不同的 action，然后你要测什么？你就是那个 flow，有些变好，有些变差，那到底应该怎么看？

所以还是应该你能再形容一下，就是这一个 evaluation。end-to-end 你再形容一次可以吗？我训练了很多 checkpoint，并生成了大量的 generated video。我需要判断哪个 checkpoint 更好，或者当前的 checkpoint 是否已经达到可以 release 的标准。

具体的 evaluation 维度包括：

1. Video Quality
   不仅是简单的 eyeballing，还需要区分 simple scene 和 complex scene。

2. Consistency
   测试转过去、转回来的表现是否一致。这涉及非常多的维度，比如左转回来、右转回来、上转回来等。

3. Action Following
   这是最困难的部分。目前模型有 23 个不同的 action（源于数据集限制，无法减少，只能去 fit 它）。
   由于 eyeballing 非常困难，必须分 task 去 validate，例如：
   (a) Movement only
   (b) Mouse only
   (c) Build only
   (d) Attack 或 Chase 等

如果让我专注处理，一天也能搞完。但如果只是运行 evaluate checkpoint 这件事，大概半小时就能扫完并做决定。

目前的操作流程是：
修改 checkpoint setting，查看凯欣的 checkpoint 路径并 load 进来（这需要一点时间）。

关于自动触发 evaluation 的问题：
之前讨论过，在训练时做 validation 会严重拖慢进度。所以现在的逻辑是：
1. 你需要一个由 checkpoint 加 prompt 组成的 evaluate video 小 pipeline。
2. 当有新的 checkpoint 时，触发这个 pipeline 生成一堆东西。
3. 此时某种意义上就可以开始 evaluation 了。

目前在训练过程中生成的 validation 只会产出一些 video 和一点 optical flow 的数据，但还没能做到分 task 处理，也缺少相关的 score，因为 task 的标注本身也需要时间。你整个数据集有多大？然后 task 标注本身要多久？

关于 evaluation task 的定义，我确实需要花一点时间来想。现在我搞了 32 个不同的 task，但还没有给它们分类，只是简单标注了比如"task W only"或者"turn left"这种。那么 32 个 video 对应的 32 个 score 该怎么判断？比如某一类的 task 表现如何，哪个 checkpoint 在哪一类 task 上更好，这些目前都还没定。

而且现在的覆盖也不够全面。我目前基本只 cover 了复杂场景，但在我的 validation 里面，简单场景反而 cover 比较少，比如左转之类的就没怎么覆盖。

关于场景和动作的复杂度：
1. Scene Complexity：我选取的基本上都是稍微复杂一点的 scene。
2. Action Complexity：动作难度这块 cover 比较少，目前共有 23 个种类，主要包括：
   (a) 上下左右
   (b) Mouse（4 个方向）
   (c) 空格（跳）
   (d) F1 到 F8（好像是取 Minecraft 底下的 box）
   (e) 加速和减速：这个比较关键。加速是组合键，按 Shift 再加上"前"。

这样组成了 23 个 combination。其实现在我们 evaluate 的最精确的主要是：前后左右、Mouse（这 8 个 action），再加上一个 Still（没有任何动作）。至于其他的 action，感觉也需要 evaluate，但这部分我们还没做。V6GEN 的一个简单的讨论。

关于 V6GEN 的 Eyeballing，目前看 A Good 就可以了。但是对于 World Model 的 Action Following 来说，它需要 Consistency 加 Action Following。按理来说，这部分可以找人做一下 Literary Survey，然后复现一下其他人的 Score 就可以，但虽然现在确实已经 Dedicate 给其他同学了，我觉得最了解这个项目的还是我，我相当于要教他们我们需要看哪些东西。

具体来说，假设我现在从零开始做一次 Training。我的 Trajectory 是：
1. 开始跑一个 Training，针对一组参数跑一个 Training。
2. 每 500 个 Step 做一次 Evaluate。
3. 我会根据一个 Metric（目前是 Optical Flow 稍高的一个 Evaluation Metric）选出最好的 5 个 Checkpoint 留下。

这里之所以维持 5 个 Checkpoint，是因为我每 500 步去 Evaluate 一次，如果它的 Score 比较好，我就会存下来。我会始终 Maintain 一个历史最好的 Top 5。

关于 Eyeballing 的时机，比如我 Train 了一万步（目前最大能存到 70K 步），我目前的策略是：
* 每 5000 步一定存一个整点的 Checkpoint。
* 同时维持一个 Best Top 5 的 Logic。

之所以需要 Eyeballing，是因为 Optical Flow 并不是非常准确。在特定的 Case 下，它对于 Still（无动作）的 Score 不准，对于"撞墙"的 Score 也不准。因为存在这种 Error，所以我必须在 Best Checkpoint 里面自己看，并拿这些去和每 5000 步整点存下来的 Checkpoint 进行 Compare。接着就是为什么需要 eyeballing，我觉得这很好理解，因为 23 个 action 你看不过来。所以我们需要一个更好的、能看得过来的 dashboard，比如一个更好的屏幕，或者说我到底要看多少。

你能帮我算一下我到底要看多少个 comparison 吗？这个我还没想清楚。所以你现在是怎么看的，可以说明一下吗？

现在因为 model performance 甚至连基本的 WISD 和 camera 都没有学好，所以还没到那一步。但慢慢地我们要真的去走 evaluation 那一步，就是把 23 个 action 进行分组，搞一些 task。比方说"加速"，我这几个 prompt 就是要 evaluate 我的 character 能不能加速。

所以你刚才的意思是，你对 task 和 prompt 没有分类？就是说你知道这个 prompt 是什么，但是目前没有加 tag，比如这个 tag 是 evaluate 人物走动、那个是加速之类的。如果是这样，其实我可以帮你做，如果你给我 dataset，我可以帮你直接跑一次，把这些 categorize 出来。或者说，任何人都可以尝试用一个 agent 去做这件事。

这个方案是 in-place 的，但它还比较远，暂时没什么用。因为现在的 bottleneck 是 model 还无法处理基本的行走一致性。它不能算远，只能说我们希望能尽快做一个 comprehensive 的 evaluation。这肯定是有帮助的。

现在的 scope 是：
1. 首先，optical flow 是你在 training 时主要用的 evaluation metric。
2. 其次，对于人来说，我在 evaluate 时是以 optical flow 做参考，主要靠 eyeballing。之所以只看 top 5，是因为 eyeballing 确实看不过来。

接下来我还没理解的是，可能你要 walkthrough 一下整个流程。Eyeballing 不好的原因是我要在不同的 task 之间 switch，导致 group 非常 sparse，而且我需要 context switch。

比方说有两个 checkpoint：
* Checkpoint A 在 1、3、5、7、9 这几个 video 上表现比较好。
* Checkpoint B 在剩下的 video 上表现好。

甚至你自己看的时候，你可能连 10 个 video 都看不到，也就比个 3 个左右，这肯定不够 sufficient。而且你比较的这 3 个应该是不同类别的。我现在 validation 是 32 个 video，每一个 video 的 action 都不一样。

目前的流程是：
1. 每个 checkpoint 会 generate 32 个 prompt 的 video。
2. 我要和其他 5 个 checkpoint 去比较，哪一个 checkpoint 在某一个类别上是最好的，并给出一个分数。
3. 我要对这 32 个 video 中的每一个，都找出最好的 checkpoint 是谁。
4. 最后综合判断哪一个 checkpoint 的 overall 表现最好。

我觉得这也没那么简单。我不知道最好的方法是什么，但我觉得可能不是简单地算一下 5 个 checkpoint 里谁拿到的"最好 video"数量最多就选谁。我还没想好具体该怎么做，所以我才说我们要看不同的 task。我当时设计这 32 个 video 的时候没有考虑 task，所以现在我在想，应该是按 task 做 score，然后去找一个各个 task 都还行的 checkpoint。

也就是说，如果我开发一个类似 Tinder 左滑右滑形式的 App，我对每一个 task 做好分类，那么在 show 给你的时候就显示一个 video 加上对应的 prompt。你可以用二倍速或者三倍速去放它，通过左滑右滑来评价这个 video 的 quality 如何，这样我就能比较快地 generate 出整个 evaluation。

我觉得目前的 bottleneck 在于分 task。我们现在只有 32 个 prompt，这并不 balance，也不能 comprehensive 地 cover 各个 task。那 32 个 prompt 是我拍脑袋想的，已经不能全面地 evaluate 了，我们可能要增加到 120 个左右。

分了 task 之后会形成不同的 group，每个 group 里的 video 数量还不确定。比如"基本操作"这个 category 可能有 8 个 video，用来 evaluate 前后左右、上下左右这些操作有多好。但我觉得可能还需要更多，因为它要 evaluate 不同 complexity 的 video。比如：
1. 表面非常平坦的地面：你应该一点错误都不准有。
2. 比较复杂的地面：可能有一些 auto jump 或者晃一下，这是 OK 的。

所以对于不同 scene 的 difficulty，会有不同的标准。当一个人要 evaluate 某一个 task 下的 sub-task 时，他要对 video 进行难易度和问题的标注。比如在一个容易的问题上，容忍度是很低的。

你可能还可以 optionally 地说明这个东西坏在哪里。比如通过语音输入直接 input 哪里有问题，然后把它划掉，对 video 本身做分类。

我的目标是：假设我不能 100% evaluate 完整个 landscape，但我可以通过 40% 的 human effort 大概了解这些 checkpoint 的优劣，或者我们的训练在什么地方出现了问题。如果我每次只聚焦于一个 video 做精确的 human eyeballing 分类，那么 App 的设计就需要一种左滑右滑的机制，提供一个好的 interface 让你能做标注或者 skip。

这对你来说是有帮助的，只是我们还没算过这个 throughput。比如一个 video 看两三秒，human quality 到底有多 reliable？我之所以用之前那个方法，是因为训练过程中它在收敛，所以肯定大概准确；但人其实不一定能收敛，人类的 evaluation 甚至会有很多 bias。

有时候我给这两个 checkpoint 各加一分，有时候给这个加一分、那个减一分。事实证明，你不能直接比较两个 checkpoint，而只能通过每一个 video 去评价这个 video 本身如何。

---

## Segment 2 — 2026-03-10T13:30:50-07:00

我在这 32 个 video 里面看到了一个有问题的东西，我就会把它排除掉。正常是因为这个，而不是说我真的去两边比较，然后算一下这个加 1，或者那个有多少个好的。

也就是说，如果现在给你干活的人有 5 个人，每一个人在 5 分钟之内能够 process 30 个 video，那如果你每次 training 结束之后给大家发这个 App，让每个人去 intersect 处理这些 video，那其实你的 Human Evaluation 大约 10 到 20 分钟就能出结果。

我感觉 Google 现在就是这么做的。他们基本上训完之后，半小时内就能出 Human Evaluation 的结果。那我们是不是也直接搞一个？

所以现在的 bottleneck 是：
1. 分 task。
2. 在 training 之后直接出 video generation 的结果。

就这样一个小 pipeline。

另外，你们现在的 video 存在哪里？是 M2 吗？那 M2 要先 stream 到某个地方。你会 upload checkpoint，WandB 上肯定有。WandB 有 checkpoint 吗？Checkpoint 没有，但是 video 是有的。你 validation 的时候就会出 checkpoint。

其实我的 video 是直接从 WandB 上得到的，WandB 会标注你这个 video 的 prompt 是什么。事实上，你只需要在这个外面包一个 category 或 task 之类的，就被 absorb 出去了。

我这边的问题是：
1. 我需要 redesign validation 的 prompt。
2. 需要删减或增加一些内容，使它真的能够按不同的 task 进行分类。

你认为这个 bottleneck 是在你这里，还是说其实任何一个有 context 的人也能干？是必须由你来 design 吗？事实上我可以 propose 三个方案给你，然后你选一个。只要我知道这个 full dataset 是什么，我就不会 block 你。

我靠，他已经整理出来了吗？

---

## Segment 3 — 2026-03-10T13:36:45-07:00

我觉得训练这一个月的一些经验还是有 benefit 的，包括什么样的 scene 是 flat scene，什么样的 scene 是 complex scene，以及这个模型能达到的能力边界。

比方说，这个模型遇到障碍物时的 default behavior 就是停下，它不会 auto-jump。那么你在 design 的时候，你的 expectation 就应该是模型不会 auto-jump。另外，这个模型基本不会有撞墙的 behavior，因为我们后来把数据分成了"不撞墙"的类型，只会让它在离障碍物比较近的时候停下。我们 filter out 了那些 obstacle flow 非常剧烈的 sample。

如果把你的经验 distill 出来，用文字表述出你对经验的描述——当你看到一个 video 后，你会 expect 一个 model 的 prediction（事实上你是在对 model 做 prediction）。假设我把你的经验转化成文字给到一个 agent，让它根据你的经验去 filter 或者选择一些 prompt 和 video。

这里的 prompt 其实是 first frame 加上 action list，所以这需要的 VLM 也要有一定的能力。事实上它不 provide 文字描述，没有文字，只有一个 frame 加 action。

它有 ground truth 吗？
有些有，也需要一些没有的。我们现在没有把有 ground truth 的数据 split 出来做 validation，现在的 validation 其实是一些全新的 image，没有 ground truth。

我觉得这个不好，应该 split 出来一些。等一下，validation 为什么会有 image 没有 ground truth 呢？
比方说同样一个 image，在人家的 dataset 里有固定的 action。但如果我想针对同一个 image 尝试往前走一下再回来，我很难在人家的 dataset 或者 human play 的 action 里面完全找到"前进五步、后退五步"这种序列。

哦，所以你要 build 这样一些东西出来。
对，相当于要自己写一些这种类型的 action。我们想测的东西不一定能在 training set 里完全找到，或者需要花时间才能找到。

那怎么样 construct 一个这样的 case 呢？比如用一个既有的 scene，如果给你一个 action list 然后你去点，能不能就这样 construct 一个？
那比较复杂了，你需要 run Minecraft 的 simulator，要人类自己在 Minecraft 里面录像。

这就是我不理解的地方。如果我已经有一个 image，直接加上个 action list，我是不是就 construct 了一个 training set 的 row？
你需要一个 video。我给定一个 image，optical flow 比较的是两个 video 的 diff。

optical flow 比较的是什么？
这个 metric 是说，你有一个 ground truth 和一个 generated video，比较这两个东西的 diff，有点像 video similarity（比如 LPIPS 那种）。

你说是 optical flow，我还以为你说 eyeballing 的时候有没有 ground truth。
这个不一定。如果是 optical flow 的话肯定有，只要给定一个 action sequence，就可以构造一个 synthetic 的 optical flow 出来。但这也就是它不 reliable 的地方：不同的 image、不同的 scene，同样的 action 产生的 optical flow 也是不一样的。比如一个 object 在这儿和在这儿，同样是前进，它的 flow 也不一样。所以 optical flow 在没有 ground truth、只有 action list 的前提下是不 reliable 的。

但 validation 现在没有办法，这是我们唯一有的一个针对 action 的 automatic metric。

也就是说，另外一种可能性是在 construct dataset 的时候，很快地把 Minecraft 的 scene generate 出来。但我没理解的问题是：如果要 construct 一个 case，它为什么这么复杂？从我的角度看，不就是直接去 Minecraft 里跑这样一个 action，把 video record 下来作为 ground truth，你就可以用了吗？
对，我需要一个人来跑这件事情。

也就是说，如果我给你一个 Minecraft server，你直接在手机上操作，把 video crop 下来做一个 dataset 的 row 就可以了？
是的。

那 Minecraft server 隔壁 WorkLab 就有一个，直接连上是不是就可以了？
是的，但我自己应该不会想做这件事情。

OK，所以这件事情并不复杂，只是 construction 的 overhead 很大。
对，对我来说 overhead 很大。

---

## Segment 4 — 2026-03-10T13:41:12-07:00

我觉得训练这一个月的一些经验还是有 benefit 的，包括什么样的 scene 是 flat scene，什么样的 scene 是 complex scene，以及这个模型能达到的能力边界。

我觉得这件事情即使有了 Ground Truth，Optical Flow 也不是完全 reliable 的。还是我刚刚说的，物体近和远导致的 Optical Flow 误差不一样。所以理论上来说，所有的 training set 在做 evaluation 时，如果你有 Ground Truth 是最好的，对吗？

在有 Ground Truth 的前提下，Optical Flow 也不是完全可靠的。那么如果有 Ground Truth，Optical Flow 是怎么 work 的？它是直接拿两个 video 的 flow 去做一个每个 pixel 的 flow 比较吗？比方说用 MSE 或 RMSE？

其实它是做一组图像的 LPIPS 的一个变种，会考虑帧与帧之间的 diff。这个就叫 Optical Flow。

如果我们认为 Optical Flow 在 validation 上是比较好的 metric，但事实上你在 validation 时 flow 都是 reference，主要问题还是为了加速 eyeballing（人工目检）。我现在理解的有几件事情可以做：

1. 自动化流程
   我们首先要能自动化地从 1B 数据集中 generalize 这些 video，通过简单的 infra 把这些东西扒出来，变成每一个 pair，让人类能够比较好地去校验。我觉得这会非常 beneficial。

2. App 功能设计
   当我有了这个 App，里面会不会显示针对某个 category 出现的问题，或者提供一些选项让 human annotate？比方说，你可以说明这些 video 会有哪些问题。
   
   这个 App 本身需要显示的内容包括：
   (a) 初始 image
   (b) Action list
   (c) 对应的 video
   (d) 选项（判断 video 的好坏比例等）

我们需要想好这个 action list 应该怎么表示。因为 23 个 action 要 overlay 到 image 上比较困难。Action list 实际上就是键盘显示的映射。我们现在的做法是将其 overlay 到 video 上，直接 generate 一个那种 video 出来。

在某一个时刻，你按一下某个 button，这个 action list 是时刻加上某一个 action。比方说 77 帧，那就是 77 个 23 维向量，这是它 raw data 的储存形式。所以这个 table 其实没有 timestamp，它就是一个 77 维的向量，每个 frame 对应一个 action。

关于标注：
比如标注 "W only"，它会按一下 W，然后松开 W，这就是 "W still"。这种情况就是 "W + still"。更复杂的其实没法标，我就标比方说 "WSD" 之类的。

妈的，也就是说，如果我能在这个 App 里面 generate 一个 action list，我可以直接用一个 checkpoint 把这个 video generator 生成出来，然后去 evaluate。假设你突发奇想说想 check 某个 case，能 automate 这个 process 肯定是最好的。虽然加东西比较复杂，但还是希望我们一开始就 build 一个 comprehensive 的东西，之后直接 refer to 这个。
