# 备课笔记 · 襄阳四中期中 Q18 · 角平分线 + 面积最优化

## 一、题目

在 $\triangle ABC$ 中，$AB = 2AC$，$AD$ 是 $\angle BAC$ 的平分线，且 $AD = kAC$。

（1）求 $k$ 的取值范围；
（2）若 $S_{\triangle ABC} = 1$，则 $k$ 为何值时，$BC$ 最短。

## 二、题目定位

- **题型**：解答题中档·三角形综合·角平分线 + 最值
- **核心考点**：面积分割法推导角平分线长、余弦定理建立 BC 的表达式、辅助角求最小值、两问之间的递推关系
- **难度**：★★★☆☆
- **分值权重**：17 分（7 + 10），第二问难度明显高于第一问

## 三、完整解法（专家版）

### 第 (1) 问

记 $AC = a$，则 $AB = 2a$，$AD = ka$。设 $\angle BAC = \alpha$，则 $AD$ 平分 $\angle BAC$，故 $\angle BAD = \angle DAC = \alpha/2$。

**面积分割**：$D$ 在 $BC$ 上，故 $S_{\triangle ABC} = S_{\triangle ABD} + S_{\triangle ACD}$。

$$\frac{1}{2} \cdot AB \cdot AC \cdot \sin\alpha = \frac{1}{2} \cdot AB \cdot AD \cdot \sin\frac{\alpha}{2} + \frac{1}{2} \cdot AC \cdot AD \cdot \sin\frac{\alpha}{2}$$

$$\frac{1}{2} \cdot 2a \cdot a \cdot \sin\alpha = \frac{1}{2} \cdot ka \cdot \sin\frac{\alpha}{2} \cdot (2a + a)$$

$$a^2 \sin\alpha = \frac{3}{2} k a^2 \sin\frac{\alpha}{2}$$

用倍角公式 $\sin\alpha = 2\sin\frac{\alpha}{2}\cos\frac{\alpha}{2}$，两边除以 $a^2\sin\frac{\alpha}{2}$（正值）：

$$2\cos\frac{\alpha}{2} = \frac{3}{2}k \implies k = \frac{4}{3}\cos\frac{\alpha}{2}$$

由于 $\alpha \in (0, \pi)$（三角形内角），故 $\frac{\alpha}{2} \in (0, \frac{\pi}{2})$，$\cos\frac{\alpha}{2} \in (0, 1)$。

$$\boxed{k \in \left(0, \frac{4}{3}\right)}$$

### 第 (2) 问

由余弦定理：

$$BC^2 = AB^2 + AC^2 - 2 \cdot AB \cdot AC \cdot \cos\alpha = 4a^2 + a^2 - 4a^2\cos\alpha = a^2(5 - 4\cos\alpha)$$

由 $S_{\triangle ABC} = \frac{1}{2} \cdot AB \cdot AC \cdot \sin\alpha = a^2\sin\alpha = 1$，得 $a^2 = \frac{1}{\sin\alpha}$。

$$BC^2 = \frac{5 - 4\cos\alpha}{\sin\alpha} =: f(\alpha)$$

**辅助角求最小值**（$\alpha \in (0, \pi)$）：

设 $y = f(\alpha)$，则 $y\sin\alpha + 4\cos\alpha = 5$，即 $\sqrt{y^2 + 16}\sin(\alpha + \varphi) = 5$（其中 $\tan\varphi = \frac{4}{y}$）。

方程有解的条件：$\sqrt{y^2 + 16} \ge 5 \implies y \ge 3$（因 $y > 0$）。

$y = 3$ 时等号成立，此时 $\sin(\alpha + \varphi) = 1$，解得 $\alpha + \varphi = \frac{\pi}{2}$，即 $\cos\alpha = \sin\varphi = \frac{4}{5}$。

验证 $\alpha \in (0, \pi)$：$\cos\alpha = \frac{4}{5} > 0$，$\alpha$ 为锐角，合法。

$BC^2_{\min} = 3$，$BC_{\min} = \sqrt{3}$。

**代回求 $k$**：

$$\cos\frac{\alpha}{2} = \sqrt{\frac{1 + \cos\alpha}{2}} = \sqrt{\frac{1 + \frac{4}{5}}{2}} = \sqrt{\frac{9}{10}} = \frac{3\sqrt{10}}{10}$$

$$k = \frac{4}{3} \cdot \frac{3\sqrt{10}}{10} = \frac{4\sqrt{10}}{10} = \frac{2\sqrt{10}}{5}$$

$$\boxed{k = \frac{2\sqrt{10}}{5}}$$

**备选：导数法**
$f(\alpha) = \frac{5 - 4\cos\alpha}{\sin\alpha}$，$f'(\alpha) = \frac{4\sin^2\alpha - (5 - 4\cos\alpha)\cos\alpha}{\sin^2\alpha} = \frac{4 - 5\cos\alpha}{\sin^2\alpha}$。

$f'(\alpha) = 0 \Rightarrow \cos\alpha = \frac{4}{5}$，与辅助角法结果一致。两种方法等价，辅助角法更适合高考语境。

## 四、前置知识清单

1. **三角形面积公式** $S = \frac{1}{2}ab\sin C$
   - 本题用法：面积分割是第一问的核心工具，连用两次
   - 熟练程度：必须

2. **倍角公式** $\sin 2\theta = 2\sin\theta\cos\theta$
   - 本题用法：$\sin\alpha = 2\sin\frac{\alpha}{2}\cos\frac{\alpha}{2}$，是推出 $k = \frac{4}{3}\cos\frac{\alpha}{2}$ 的关键一步
   - 熟练程度：必须，条件反射级

3. **余弦定理** $c^2 = a^2 + b^2 - 2ab\cos C$
   - 本题用法：第二问建立 $BC^2$ 关于 $\alpha$ 的表达式
   - 熟练程度：必须

4. **辅助角公式** $a\sin\theta + b\cos\theta = \sqrt{a^2 + b^2}\sin(\theta + \varphi)$
   - 本题用法：将 $y\sin\alpha + 4\cos\alpha = 5$ 变形后求 $y$ 最小值
   - 熟练程度：必须理解，尤其是"方程有解 $\Leftrightarrow$ 振幅 $\ge$ 右端"这个逻辑

5. **半角公式** $\cos^2\frac{\theta}{2} = \frac{1 + \cos\theta}{2}$
   - 本题用法：从 $\cos\alpha = \frac{4}{5}$ 反推 $\cos\frac{\alpha}{2}$，最后算 $k$
   - 熟练程度：必须，且方向是从 $\cos\alpha$ 求 $\cos\frac{\alpha}{2}$（与倍角方向相反）

## 五、学生卡点地图

### 卡点 1：第一问选错工具
- **位置**：一上手
- **原因**：学生知道"角平分线定理" $BD/DC = AB/AC = 2/1$，但角平分线定理给的是 $D$ 的位置，不是 $AD$ 的长度，跑偏了
- **破解**：$AD$ 是一条线段的长度，$k = AD/AC$。要建立含 $AD$ 的方程，面积分割是最自然的选择——$D$ 在 $BC$ 上，$\triangle ABC$ 自然被 $AD$ 切成两份

### 卡点 2：面积公式里角度写错
- **位置**：写 $S_{\triangle ABD}$ 时
- **原因**：$\triangle ABD$ 包含顶角 $\angle BAD = \alpha/2$，而不是 $\angle BAC = \alpha$；学生把 $\sin\alpha$ 写成 $\sin\alpha/2$ 的公式里混用
- **破解**：明确哪个三角形、对应哪个夹角。$S_{\triangle ABD} = \frac{1}{2} \cdot AB \cdot AD \cdot \sin(\angle BAD) = \frac{1}{2} \cdot AB \cdot AD \cdot \sin\frac{\alpha}{2}$

### 卡点 3：倍角消元的时机
- **位置**：面积等式化简后
- **原因**：等式 $a^2\sin\alpha = \frac{3}{2}ka^2\sin\frac{\alpha}{2}$ 出来后，学生可能直接解 $k$ 而忘了用倍角消掉 $\sin\alpha$
- **破解**：$\sin\alpha$ 和 $\sin\frac{\alpha}{2}$ 不是同一个量，不能直接除。必须先展开 $\sin\alpha = 2\sin\frac{\alpha}{2}\cos\frac{\alpha}{2}$，再两边除以 $\sin\frac{\alpha}{2}$

### 卡点 4：第二问变量分析
- **位置**：第二问开始
- **原因**：$S_{\triangle ABC} = 1$ 给定了一个约束，但 $a$（即 $AC$）和 $\alpha$ 仍然都是自由变量；学生可能以为两个约束（$AB = 2AC$ + $S = 1$）足以确定三角形，但还差一个自由度
- **破解**：用 $S = 1$ 把 $a^2$ 用 $\alpha$ 表示，消掉 $a$，这样 $BC^2$ 就成了关于单变量 $\alpha$ 的函数，可以求最值

### 卡点 5：辅助角法"方程有解"的逻辑方向
- **位置**：辅助角变形后
- **原因**：$\sqrt{y^2 + 16}\sin(\alpha + \varphi) = 5$，学生可能以为 $y$ 越大越好，或者分不清是求 $y$ 的最小值还是最大值
- **破解**：$\sin(\alpha + \varphi) = \frac{5}{\sqrt{y^2 + 16}} \le 1$ $\Rightarrow$ $y^2 + 16 \ge 25$ $\Rightarrow$ $y \ge 3$。$y$ 是 $BC^2$，我们要求 $BC$ 最短就是求 $y$ 最小，即 $y = 3$

### 卡点 6：最后用半角公式反推 k
- **位置**：第二问最后
- **原因**：学生算出 $\cos\alpha = 4/5$ 后忘了代回第一问的 $k = \frac{4}{3}\cos\frac{\alpha}{2}$，直接写完就交卷，丢最后一步分
- **破解**：提醒第二问问的是"$k$ 为何值"，不是"$\alpha$ 为何值"——必须用半角公式把 $\cos\frac{\alpha}{2}$ 算出来

## 六、关键跳跃点（Why 慢镜头）

### 跳跃 1：为什么用面积分割法推导 AD
- **表象**：直接写 $S_{\triangle ABC} = S_{\triangle ABD} + S_{\triangle ACD}$
- **Why**：$AD$ 是 $\angle BAC$ 的平分线，$D$ 在 $BC$ 上。三角形被 $AD$ 切成两个小三角形，它们共享一条边 $AD$，且各自有一个夹角是 $\alpha/2$。这就把 $AD$ 自然地带入了面积公式。如果改用余弦定理，还需要知道 $BD$ 和 $CD$，引入新的未知量，不如面积法直接。
- **迁移价值**：含有角平分线 $AD$ 长度的问题，**面积分割** 永远是第一选择——$D$ 在 $BC$ 上这个条件天然给出 $S_{\triangle ABC} = S_{\triangle ABD} + S_{\triangle ACD}$。
- **样板台词**：「$AD$ 是角平分线，$D$ 在 $BC$ 上——这个条件天生适合面积分割。两个小三角形共享 $AD$，各自用 $AD$ 和相邻边面积公式，$k$ 自然出来了。」

### 跳跃 2：第二问如何把双变量问题变成单变量
- **表象**：利用 $S = 1$ 把 $a^2 = \frac{1}{\sin\alpha}$ 代入，使 $BC^2$ 只含 $\alpha$
- **Why**：$S_{\triangle ABC} = a^2\sin\alpha = 1$ 是一个约束，本来 $a$ 和 $\alpha$ 都自由，但这个约束把 $a^2$ 固定为 $\frac{1}{\sin\alpha}$ 的函数，从而消掉一个自由度。消掉 $a$ 后，$BC^2$ 变成关于单变量 $\alpha$ 的函数，最值问题就可以处理了。
- **迁移价值**：**约束方程 = 消元工具**。遇到多变量最值问题，先数有几个自由度，约束方程能消几个，一般会消到单变量再求最值。

### 跳跃 3：辅助角法求最值的逻辑
- **表象**：$y\sin\alpha + 4\cos\alpha = 5 \Rightarrow \sqrt{y^2 + 16} \ge 5 \Rightarrow y \ge 3$
- **Why**：把含有 $y$（待求最小值）的等式，变形成"方程 $\sin(\alpha + \varphi) = \frac{5}{\sqrt{y^2+16}}$ 对某 $\alpha \in (0, \pi)$ 有解"。$\sin$ 值最大为 1，所以右端必须 $\le 1$，即 $\sqrt{y^2+16} \ge 5$，这给出 $y \ge 3$。$y = 3$ 时恰好在 $\alpha$ 的范围内有解，所以 3 就是最小值。
- **迁移价值**：辅助角法不只用来化简，还可以用来**解最值问题**——把最值问题化为"某三角方程有解的条件"，是一类重要的转化思维。

## 七、易错点

1. **面积公式选错夹角**：$S_{\triangle ABD}$ 的夹角是 $\angle BAD = \alpha/2$，不是 $\alpha$

2. **忘用倍角公式**：$\sin\alpha = 2\sin\frac{\alpha}{2}\cos\frac{\alpha}{2}$，若不用这步就无法消掉 $\sin\frac{\alpha}{2}$ 化简

3. **第二问末尾忘代回 k**：题目问的是 $k$ 而不是角，必须把 $\cos\alpha = 4/5$ 通过半角公式转化为 $k$

4. **半角公式方向不熟**：常见的是 $\cos 2\theta$ 用 $\cos\theta$ 表示；本题反过来，由 $\cos\alpha$ 求 $\cos\frac{\alpha}{2}$，用 $\cos\frac{\alpha}{2} = \sqrt{\frac{1+\cos\alpha}{2}}$（取正是因为 $\frac{\alpha}{2} \in (0, \frac{\pi}{2})$）

5. **$y$ 的正负**：$BC^2 = y > 0$，辅助角变形后 $\tan\varphi = 4/y > 0$，$\varphi \in (0, \frac{\pi}{2})$ 合法

## 八、核心心法

### 心法 1：角平分线长度 → 面积分割

**含角平分线长度的问题，面积分割是标配工具：$D$ 在 $BC$ 上 $\Rightarrow$ $S_{\triangle ABD} + S_{\triangle ACD} = S_{\triangle ABC}$，两个小三角形都含 $AD$ 和半角 $\frac{\alpha}{2}$，把 $k$ 自然带出来。**

迁移：不只在"比例条件"题里，凡是需要建立含有 $AD$ 长度的方程，优先考虑面积路径。

### 心法 2：约束消变量，多变量变单变量

**遇到多变量最值，先数清楚约束方程，用约束消掉多余变量，把问题化成单变量函数的最值。**

本题：$AB = 2AC$（一个约束），$S = 1$（第二个约束），两个约束消掉 $a$ 之后，$BC^2$ 只剩 $\alpha$。

### 心法 3：辅助角法的"有解逻辑"

**$a\sin\theta + b\cos\theta = c$（$c$ 不含 $\theta$）$\Leftrightarrow \sqrt{a^2+b^2}\sin(\theta+\varphi)=c$，有解条件是 $\sqrt{a^2+b^2} \ge |c|$。当 $c$ 是待求最值的量时，这个有解条件就是最值约束。**

## 九、讲解推荐路径

1. **读题 + 题目画像**
   - 两小问：第一问求范围，第二问最值
   - 关键：两问通过 $k = \frac{4}{3}\cos\frac{\alpha}{2}$ 衔接——第二问的结果依赖第一问推出的公式

2. **第一问：面积分割建立方程**
   - 画图，标出 $D$ 在 $BC$ 上
   - 面积分割：$S_{\triangle ABC} = S_{\triangle ABD} + S_{\triangle ACD}$
   - 代入面积公式 + $AB = 2AC$，整理
   - 倍角公式消 $\sin\alpha$，推出 $k = \frac{4}{3}\cos\frac{\alpha}{2}$

3. **第一问：确定范围**
   - 分析 $\frac{\alpha}{2}$ 的范围 $\Rightarrow \cos\frac{\alpha}{2} \in (0, 1) \Rightarrow k \in (0, \frac{4}{3})$

4. **第二问：建立 $BC^2$ 的表达式**
   - 余弦定理 $BC^2 = a^2(5 - 4\cos\alpha)$
   - $S = 1 \Rightarrow a^2 = \frac{1}{\sin\alpha}$，代入消 $a$
   - 得 $BC^2 = \frac{5 - 4\cos\alpha}{\sin\alpha}$

5. **第二问：辅助角法求最小值**
   - 设 $y = BC^2$，整理成 $y\sin\alpha + 4\cos\alpha = 5$
   - 辅助角变形，"有解 $\Rightarrow y \ge 3$"
   - 等号成立条件：$\cos\alpha = \frac{4}{5}$

6. **第二问：代回求 $k$**
   - 半角公式 $\cos\frac{\alpha}{2} = \frac{3\sqrt{10}}{10}$
   - $k = \frac{4}{3} \cdot \frac{3\sqrt{10}}{10} = \frac{2\sqrt{10}}{5}$

7. **升华：两条心法**

## 十、备注

- **画图必做**：要在 $\triangle ABC$ 中标出 $D$ 在 $BC$ 上，$AD$ 是角平分线，$\angle BAD = \angle DAC = \alpha/2$。这张图是第一问面积分割的视觉基础。
- **两问的衔接**：第一问推出的 $k = \frac{4}{3}\cos\frac{\alpha}{2}$ 是第二问的关键接口。讲完第一问要明确板书保留这个式子，不要清屏，第二问算出 $\cos\alpha$ 后直接查表代入。
- **辅助角法可用导数法替代**，但高中语境里辅助角法更标准，不需要求导。
- 得分细则中提到"$BC$ 表示出来给 13 分"，说明 $BC^2 = \frac{5-4\cos\alpha}{\sin\alpha}$ 这一步写出来是关键得分点，讲解时要特别强调。
