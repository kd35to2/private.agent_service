<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import {
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FileText,
  FolderOpen,
  Layers,
  LoaderCircle,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Square,
  Trash2,
  Upload,
  UserRound,
  X,
} from "@lucide/vue";
import { api, ApiError, checkedResponse, errorText, jsonBody } from "./api";
import { readStream } from "./stream";
import { markdown } from "./markdown";
import { vFocusDialog } from "./focusDialog";
import type {
  ChatMessage,
  Chunk,
  Evidence,
  KnowledgeDocument,
  SearchResult,
  ServiceInfo,
  SourceChunk,
  Thread,
  UploadResult,
  User,
} from "./types";

type Page = "chat" | "documents" | "search" | "account";
const user = ref<User | null>(null);
const booting = ref(true);
const bootError = ref("");
const page = ref<Page>("chat");
const mobileNav = ref(false);
const notice = ref("");
const warning = ref("");
const authMode = ref<"login" | "register">("login");
const username = ref("");
const password = ref("");
const confirmPassword = ref("");
const authError = ref("");
const authBusy = ref(false);
const documents = ref<KnowledgeDocument[]>([]);
const docsLoading = ref(false);
const docFilter = ref("");
const threads = ref<Thread[]>([]);
const messages = ref<ChatMessage[]>([]);
const historyLoading = ref(false);
const threadId = ref("");
const draft = ref("");
const streaming = ref(false);
const streamPhase = ref("正在连接");
const chatError = ref("");
const model = ref("");
const models = ref<string[]>([]);
const chatEnd = ref<HTMLElement | null>(null);
const searchQuery = ref("");
const searchLimit = ref(5);
const searchResult = ref<SearchResult | null>(null);
const searching = ref(false);
const searchError = ref("");
const drawer = ref<"chunks" | "source" | null>(null);
const selectedDoc = ref<KnowledgeDocument | null>(null);
const chunks = ref<Chunk[]>([]);
const chunkOffset = ref(0);
const drawerLoading = ref(false);
const drawerError = ref("");
const source = ref<SourceChunk | null>(null);
const uploadOpen = ref(false);
const uploadTarget = ref<KnowledgeDocument | null>(null);
const uploadFiles = ref<File[]>([]);
const uploadResults = ref<{ name: string; state: string; failed: boolean }[]>(
  [],
);
const uploadBusy = ref(false);
const dragging = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const pendingDelete = ref<KnowledgeDocument | null>(null);
const docBusy = ref("");
const currentPassword = ref("");
const newPassword = ref("");
const repeatPassword = ref("");
const accountBusy = ref(false);
const accountError = ref("");
let controller: AbortController | null = null;
let generation = 0;
let drawerGeneration = 0;

const titles: Record<Page, string> = {
  chat: "知识问答",
  documents: "我的文档",
  search: "检索验证",
  account: "账号设置",
};
const visibleDocs = computed(() =>
  documents.value.filter((d) =>
    d.name.toLowerCase().includes(docFilter.value.toLowerCase()),
  ),
);
const totalChunks = computed(() =>
  documents.value.reduce((sum, d) => sum + d.chunk_count, 0),
);
const visibleMessages = computed(() =>
  messages.value.filter(
    (m) =>
      m.type === "human" ||
      (m.type === "ai" && m.content && !m.tool_calls?.length),
  ),
);
const readyDocs = computed(
  () => documents.value.filter((d) => d.status === "ready").length,
);
const activeThread = computed(() =>
  threads.value.find((t) => t.thread_id === threadId.value),
);

function go(value: Page) {
  page.value = value;
  mobileNav.value = false;
  warning.value = "";
  notice.value = "";
  if (value === "documents") void loadDocs();
}
function statusLabel(value: string) {
  return (
    (
      { ready: "已就绪", processing: "处理中", failed: "处理失败" } as Record<
        string,
        string
      >
    )[value] || "待处理"
  );
}
function locationLabel(item: { page: number | null; chunk_index: number }) {
  return item.page != null
    ? `第 ${item.page} 页 · 片段 ${item.chunk_index}`
    : `片段 ${item.chunk_index}`;
}
function dateLabel(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}
function resetPrivateState() {
  generation++;
  drawerGeneration++;
  controller?.abort();
  controller = null;
  user.value = null;
  documents.value = [];
  threads.value = [];
  messages.value = [];
  threadId.value = "";
  searchResult.value = null;
  searchQuery.value = "";
  draft.value = "";
  drawer.value = null;
  source.value = null;
  chunks.value = [];
  selectedDoc.value = null;
  uploadTarget.value = null;
  pendingDelete.value = null;
  uploadOpen.value = false;
  uploadFiles.value = [];
  uploadResults.value = [];
  streaming.value = false;
  historyLoading.value = false;
  docsLoading.value = false;
  searching.value = false;
  drawerLoading.value = false;
  drawerError.value = "";
  docFilter.value = "";
  mobileNav.value = false;
  accountError.value = "";
  password.value = "";
  confirmPassword.value = "";
  currentPassword.value = "";
  newPassword.value = "";
  repeatPassword.value = "";
  warning.value = "";
  notice.value = "";
  chatError.value = "";
  searchError.value = "";
  page.value = "chat";
}
function expire() {
  resetPrivateState();
  authError.value = "登录已过期，请重新登录。";
}
async function loadDocs() {
  const current = generation;
  docsLoading.value = true;
  try {
    const result = await api<{ documents: KnowledgeDocument[] }>(
      "/knowledge/documents",
    );
    if (current === generation) documents.value = result.documents;
  } catch (error) {
    if (current === generation) warning.value = errorText(error);
  } finally {
    if (current === generation) docsLoading.value = false;
  }
}
async function loadThreads() {
  const current = generation;
  try {
    const result = await api<{ threads: Thread[] }>(
      "/rag-assistant/threads?limit=50",
    );
    if (current === generation) threads.value = result.threads;
  } catch (error) {
    if (current === generation) warning.value = errorText(error);
  }
}
async function loadWorkspace() {
  const current = generation;
  await Promise.all([
    loadDocs(),
    loadThreads(),
    (async () => {
      try {
        const info = await api<ServiceInfo>("/info");
        if (current === generation) {
          models.value = info.models;
          model.value = info.default_model;
        }
      } catch (error) {
        if (current === generation) warning.value = errorText(error);
      }
    })(),
  ]);
}
async function bootstrap() {
  booting.value = true;
  bootError.value = "";
  try {
    user.value = await api<User>("/auth/me");
    await loadWorkspace();
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401))
      bootError.value = errorText(error);
  } finally {
    booting.value = false;
  }
}
async function authenticate() {
  authError.value = "";
  if (!/^[a-z0-9_.-]{3,32}$/.test(username.value.trim().toLowerCase())) {
    authError.value = "用户名需为 3–32 位字母、数字、下划线、点或短横线。";
    return;
  }
  if (
    authMode.value === "register" &&
    password.value !== confirmPassword.value
  ) {
    authError.value = "两次输入的密码不一致。";
    return;
  }
  authBusy.value = true;
  try {
    const credentials = {
      username: username.value.trim().toLowerCase(),
      password: password.value,
    };
    if (authMode.value === "register")
      await api("/auth/register", jsonBody(credentials));
    const result = await api<{ user: User }>(
      "/auth/login",
      jsonBody(credentials),
    );
    resetPrivateState();
    user.value = result.user;
    authError.value = "";
    await loadWorkspace();
  } catch (error) {
    authError.value = errorText(error);
  } finally {
    authBusy.value = false;
  }
}
async function logout() {
  accountBusy.value = true;
  try {
    await api("/auth/logout", { method: "POST" });
    resetPrivateState();
    authError.value = "";
  } catch (error) {
    warning.value = errorText(error);
  } finally {
    accountBusy.value = false;
  }
}
async function changePassword() {
  accountError.value = "";
  if (newPassword.value !== repeatPassword.value) {
    accountError.value = "两次输入的新密码不一致。";
    return;
  }
  accountBusy.value = true;
  try {
    await api(
      "/auth/change-password",
      jsonBody({
        current_password: currentPassword.value,
        new_password: newPassword.value,
      }),
    );
    resetPrivateState();
    authError.value = "密码已修改，所有登录已失效，请使用新密码登录。";
  } catch (error) {
    accountError.value = errorText(error);
  } finally {
    accountBusy.value = false;
  }
}
async function scrollChat() {
  await nextTick();
  chatEnd.value?.scrollIntoView({ behavior: "smooth", block: "end" });
}
function onComposerEnter(event: KeyboardEvent) {
  if (event.isComposing) return;
  event.preventDefault();
  void sendMessage();
}
function newChat() {
  if (streaming.value || historyLoading.value) return;
  threadId.value = "";
  messages.value = [];
  draft.value = "";
  chatError.value = "";
  go("chat");
}
async function openThread(thread: Thread) {
  if (streaming.value || historyLoading.value) return;
  const current = generation;
  threadId.value = thread.thread_id;
  messages.value = [];
  chatError.value = "";
  go("chat");
  historyLoading.value = true;
  try {
    const result = await api<{ messages: ChatMessage[] }>(
      "/rag-assistant/history",
      jsonBody({ thread_id: thread.thread_id }),
    );
    if (current === generation) {
      messages.value = result.messages;
      void scrollChat();
    }
  } catch (error) {
    if (current === generation) chatError.value = errorText(error);
  } finally {
    if (current === generation) historyLoading.value = false;
  }
}
async function sendMessage(suggestion?: string) {
  const message = (suggestion || draft.value).trim();
  if (!message || streaming.value || historyLoading.value) return;
  if (!threadId.value) threadId.value = crypto.randomUUID();
  const current = generation;
  draft.value = "";
  chatError.value = "";
  streaming.value = true;
  streamPhase.value = "正在检索你的知识库";
  messages.value.push({ type: "human", content: message });
  controller = new AbortController();
  let tokenMessage: ChatMessage | null = null;
  void scrollChat();
  try {
    const response = await checkedResponse("/rag-assistant/stream", {
      ...jsonBody({
        message,
        thread_id: threadId.value,
        model: model.value || undefined,
        stream_tokens: true,
      }),
      signal: controller.signal,
    });
    await readStream(response, (event) => {
      if (current !== generation) return;
      if (event.type === "token") {
        if (!tokenMessage) {
          tokenMessage = { type: "ai", content: "" };
          messages.value.push(tokenMessage);
          tokenMessage = messages.value[messages.value.length - 1]!;
        }
        tokenMessage.content += event.content;
      } else if (event.type === "message") {
        if (event.content.type === "human") return;
        if (event.content.type === "tool")
          streamPhase.value = "检索完成，正在整理回答";
        if (
          tokenMessage &&
          event.content.type === "ai" &&
          !event.content.tool_calls?.length
        ) {
          messages.value.pop();
          tokenMessage = null;
        }
        messages.value.push(event.content);
      }
      void scrollChat();
    });
  } catch (error) {
    if (current === generation)
      chatError.value =
        error instanceof DOMException && error.name === "AbortError"
          ? "已停止等待。服务端可能仍在处理，可稍后重新打开此会话查看结果。"
          : errorText(error);
  } finally {
    if (current === generation) {
      streaming.value = false;
      controller = null;
      await loadThreads();
      void scrollChat();
    }
  }
}
async function runSearch() {
  if (!searchQuery.value.trim() || searching.value) return;
  const current = generation;
  searching.value = true;
  searchError.value = "";
  searchResult.value = null;
  try {
    const result = await api<SearchResult>(
      "/knowledge/search",
      jsonBody({ query: searchQuery.value.trim(), limit: searchLimit.value }),
    );
    if (current === generation) searchResult.value = result;
  } catch (error) {
    if (current === generation) searchError.value = errorText(error);
  } finally {
    if (current === generation) searching.value = false;
  }
}
async function previewDoc(doc: KnowledgeDocument, offset = 0) {
  selectedDoc.value = doc;
  chunkOffset.value = offset;
  drawer.value = "chunks";
  drawerLoading.value = true;
  drawerError.value = "";
  chunks.value = [];
  const current = ++drawerGeneration;
  try {
    const result = await api<{ chunks: Chunk[] }>(
      `/knowledge/documents/${encodeURIComponent(doc.id)}/chunks?offset=${offset}&limit=10`,
    );
    if (current === drawerGeneration) chunks.value = result.chunks;
  } catch (error) {
    if (current === drawerGeneration) drawerError.value = errorText(error);
  } finally {
    if (current === drawerGeneration) drawerLoading.value = false;
  }
}
async function previewSource(evidence: Evidence) {
  drawer.value = "source";
  source.value = null;
  drawerError.value = "";
  drawerLoading.value = true;
  const current = ++drawerGeneration;
  try {
    const result = await api<SourceChunk>(
      `/knowledge/documents/${encodeURIComponent(evidence.document_id)}/chunks/${encodeURIComponent(evidence.chunk_id)}`,
    );
    if (current === drawerGeneration) source.value = result;
  } catch (error) {
    if (current === drawerGeneration) drawerError.value = errorText(error);
  } finally {
    if (current === drawerGeneration) drawerLoading.value = false;
  }
}
function closeDrawer() {
  drawerGeneration++;
  drawer.value = null;
}
function openUpload(target: KnowledgeDocument | null = null) {
  uploadTarget.value = target;
  uploadFiles.value = [];
  uploadResults.value = [];
  uploadOpen.value = true;
}
function selectFiles(files: FileList | null) {
  if (!files || uploadBusy.value) return;
  uploadFiles.value = uploadTarget.value
    ? Array.from(files).slice(0, 1)
    : Array.from(files);
  uploadResults.value = [];
}
function onDrop(event: DragEvent) {
  event.preventDefault();
  dragging.value = false;
  selectFiles(event.dataTransfer?.files || null);
}
async function upload() {
  if (!uploadFiles.value.length || uploadBusy.value) return;
  const current = generation;
  uploadBusy.value = true;
  uploadResults.value = uploadFiles.value.map((f) => ({
    name: f.name,
    state: "等待处理",
    failed: false,
  }));
  try {
    for (const [index, file] of uploadFiles.value.entries()) {
      if (current !== generation) break;
      const row = uploadResults.value[index]!;
      row.state = "正在上传、切分并建立索引…";
      const form = new FormData();
      form.append("file", file);
      if (uploadTarget.value) form.append("document_id", uploadTarget.value.id);
      try {
        const result = await api<UploadResult>("/knowledge/documents", {
          method: "POST",
          body: form,
        });
        if (current === generation)
          row.state = result.duplicate
            ? "内容已存在，无需重复导入"
            : `已就绪 · ${result.chunk_count ?? 0} 个片段`;
      } catch (error) {
        if (current === generation) {
          row.state = errorText(error);
          row.failed = true;
        }
      }
    }
    if (current === generation) {
      uploadFiles.value = [];
      await loadDocs();
    }
  } finally {
    uploadBusy.value = false;
  }
}
async function reindex(doc: KnowledgeDocument) {
  if (docBusy.value) return;
  const current = generation;
  docBusy.value = doc.id;
  try {
    await api(`/knowledge/documents/${encodeURIComponent(doc.id)}/reindex`, {
      method: "POST",
    });
    if (current === generation) {
      notice.value = "索引已重建。";
      await loadDocs();
    }
  } catch (error) {
    if (current === generation) warning.value = errorText(error);
  } finally {
    docBusy.value = "";
  }
}
async function deleteDoc() {
  const doc = pendingDelete.value;
  if (!doc || docBusy.value) return;
  const current = generation;
  docBusy.value = doc.id;
  try {
    await api(`/knowledge/documents/${encodeURIComponent(doc.id)}`, {
      method: "DELETE",
    });
    if (current === generation) {
      pendingDelete.value = null;
      notice.value = "文档已删除，检索索引已同步。";
      await loadDocs();
    }
  } catch (error) {
    if (current === generation) {
      pendingDelete.value = null;
      warning.value = errorText(error);
    }
  } finally {
    docBusy.value = "";
  }
}
async function checkIdentity() {
  if (!user.value) return;
  const current = generation;
  const previous = user.value.id;
  try {
    const result = await api<User>("/auth/me");
    if (current === generation && user.value && result.id !== previous) {
      resetPrivateState();
      user.value = result;
      await loadWorkspace();
    }
  } catch (error) {
    if (
      current === generation &&
      error instanceof ApiError &&
      error.status === 401
    )
      expire();
  }
}
onMounted(() => {
  void bootstrap();
  window.addEventListener("session-expired", expire);
  window.addEventListener("focus", checkIdentity);
});
onUnmounted(() => {
  controller?.abort();
  window.removeEventListener("session-expired", expire);
  window.removeEventListener("focus", checkIdentity);
});
</script>

<template>
  <div v-if="booting" class="boot">
    <div class="brand-mark"><BookOpen :size="26" /></div>
    <LoaderCircle class="spin" :size="20" /><span>正在打开你的知识空间</span>
  </div>
  <div v-else-if="!user" class="auth-layout">
    <section class="auth-story">
      <a class="brand"
        ><span class="brand-mark"><BookOpen :size="24" /></span
        ><span
          >知页<span class="brand-caption">KNOWLEDGE WORKSPACE</span></span
        ></a
      >
      <div class="auth-story-body">
        <span class="eyebrow light">YOUR KNOWLEDGE, CONNECTED.</span>
        <h1>让每一页知识，<br />成为有据可循的回答。</h1>
        <p>收好文档，提出问题。<br />从分散的信息中，找到属于你的答案。</p>
        <div class="book-art" aria-hidden="true">
          <div class="paper paper-back"></div>
          <div class="paper paper-front">
            <span class="paper-label">知识，始于一页。</span>
            <div class="paper-line long"></div>
            <div class="paper-line"></div>
            <div class="paper-line short"></div>
            <div class="paper-quote">“</div>
            <span class="art-pill"><Check :size="14" /> 回答有出处</span>
          </div>
          <div class="art-spark">✳</div>
        </div>
      </div>
      <div class="auth-foot">
        <ShieldCheck :size="16" /> 私人文档 · 独立会话 · 可追溯引用
      </div>
    </section>
    <main class="auth-main">
      <div class="auth-form-wrap">
        <span class="eyebrow">WELCOME TO 知页</span>
        <h2>{{ authMode === "login" ? "欢迎回来" : "开始积累你的知识" }}</h2>
        <p class="muted">
          {{
            authMode === "login"
              ? "登录后，继续与你的知识对话。"
              : "创建账号，建立属于自己的文档空间。"
          }}
        </p>
        <div class="auth-tabs">
          <button
            :class="{ active: authMode === 'login' }"
            @click="
              authMode = 'login';
              authError = '';
            "
          >
            登录</button
          ><button
            :class="{ active: authMode === 'register' }"
            @click="
              authMode = 'register';
              authError = '';
            "
          >
            注册
          </button>
        </div>
        <div v-if="bootError" class="alert error" role="alert">
          {{ bootError }}
          <button class="text-button" @click="bootstrap">重试连接</button>
        </div>
        <form @submit.prevent="authenticate">
          <label
            >用户名<input
              v-model="username"
              name="username"
              autocomplete="username"
              placeholder="输入用户名"
              required
              minlength="3"
              maxlength="32"
              :disabled="authBusy" /></label
          ><label
            >密码<input
              v-model="password"
              name="password"
              type="password"
              :autocomplete="
                authMode === 'login' ? 'current-password' : 'new-password'
              "
              placeholder="输入密码，至少 8 位"
              required
              minlength="8"
              maxlength="128"
              :disabled="authBusy" /></label
          ><label v-if="authMode === 'register'"
            >确认密码<input
              v-model="confirmPassword"
              type="password"
              autocomplete="new-password"
              placeholder="再次输入密码"
              required
              minlength="8"
              maxlength="128"
              :disabled="authBusy"
          /></label>
          <div v-if="authError" class="alert error" role="alert">
            {{ authError }}
          </div>
          <button class="button primary auth-submit" :disabled="authBusy">
            <LoaderCircle v-if="authBusy" :size="17" class="spin" />{{
              authBusy
                ? "正在处理"
                : authMode === "login"
                  ? "进入知识空间"
                  : "创建账号并登录"
            }}<ArrowUpRight v-if="!authBusy" :size="18" />
          </button>
        </form>
        <p class="auth-hint">
          <ShieldCheck :size="15" /> 登录后仅能访问自己账号下的知识与会话
        </p>
      </div>
      <span class="auth-bottom">知页 · 把信息留下，让知识发生。</span>
    </main>
  </div>
  <div v-else class="workspace">
    <button
      v-if="mobileNav"
      class="nav-scrim"
      aria-label="关闭菜单"
      @click="mobileNav = false"
    ></button>
    <aside
      class="sidebar"
      :class="{ open: mobileNav }"
      :inert="!!drawer || uploadOpen || !!pendingDelete"
    >
      <a class="brand" href="#" @click.prevent="go('chat')"
        ><span class="brand-mark"><BookOpen :size="23" /></span
        ><span
          >知页<span class="brand-caption">KNOWLEDGE WORKSPACE</span></span
        ></a
      >
      <button
        class="new-chat"
        :disabled="streaming || historyLoading"
        @click="newChat"
      >
        <Plus :size="18" /> 开始新对话
      </button>
      <span class="sidebar-label">工作空间</span>
      <nav>
        <button :class="{ active: page === 'chat' }" @click="go('chat')">
          <MessageSquare :size="18" />知识问答<span
            class="nav-dot"
            v-if="page === 'chat'"
          ></span></button
        ><button
          :class="{ active: page === 'documents' }"
          @click="go('documents')"
        >
          <FolderOpen :size="18" />我的文档<span class="nav-count">{{
            documents.length
          }}</span></button
        ><button :class="{ active: page === 'search' }" @click="go('search')">
          <Search :size="18" />检索验证
        </button>
      </nav>
      <div class="history-head">
        <span class="sidebar-label">最近对话</span
        ><button class="icon-button" aria-label="刷新会话" @click="loadThreads">
          <RefreshCw :size="13" />
        </button>
      </div>
      <div class="thread-list">
        <p v-if="!threads.length" class="sidebar-empty">
          你的第一个问题，从这里开始。
        </p>
        <button
          v-for="thread in threads"
          :key="thread.thread_id"
          :class="{
            selected: threadId === thread.thread_id && page === 'chat',
          }"
          :disabled="streaming || historyLoading"
          @click="openThread(thread)"
        >
          <MessageSquare :size="14" /><span>{{
            thread.title || "未命名对话"
          }}</span>
        </button>
      </div>
      <div class="sidebar-bottom">
        <div class="private-note">
          <ShieldCheck :size="16" /><span
            >你的私人知识空间<small>文档与会话按账号隔离</small></span
          >
        </div>
        <button class="user-menu" @click="go('account')">
          <span class="avatar">{{
            user.username.slice(0, 1).toUpperCase()
          }}</span
          ><span class="user-name"
            >{{ user.username }}<small>个人账号</small></span
          ><Settings :size="17" />
        </button>
      </div>
    </aside>
    <div class="main-shell" :inert="!!drawer || uploadOpen || !!pendingDelete">
      <header class="topbar">
        <div class="breadcrumb">
          <button
            class="icon-button mobile-menu"
            aria-label="打开菜单"
            @click="mobileNav = true"
          >
            <Menu :size="20" /></button
          ><span>我的工作空间</span><ChevronRight :size="13" /><strong>{{
            titles[page]
          }}</strong>
        </div>
        <div class="topbar-right">
          <span class="private-badge"><span></span>私人空间</span
          ><button
            class="icon-button"
            aria-label="账号设置"
            @click="go('account')"
          >
            <UserRound :size="18" />
          </button>
        </div>
      </header>
      <div
        v-if="warning || notice"
        class="global-notice"
        :class="{ error: warning }"
        role="status"
      >
        <span>{{ warning || notice }}</span
        ><button
          class="icon-button"
          aria-label="关闭提示"
          @click="
            warning = '';
            notice = '';
          "
        >
          <X :size="16" />
        </button>
      </div>

      <main v-if="page === 'chat'" class="chat-page">
        <div class="chat-toolbar">
          <div>
            <span class="section-kicker">ASK YOUR KNOWLEDGE</span>
            <h2>{{ activeThread?.title || "知识问答" }}</h2>
          </div>
          <label class="model-picker"
            ><Sparkles :size="14" /><select
              v-model="model"
              :disabled="streaming"
              aria-label="选择回答模型"
            >
              <option v-for="item in models" :key="item" :value="item">
                {{ item }}
              </option>
              <option v-if="!models.length" value="">服务默认模型</option>
            </select></label
          >
        </div>
        <div class="conversation">
          <div
            v-if="!visibleMessages.length && !historyLoading"
            class="chat-welcome"
          >
            <div class="welcome-symbol">
              <BookOpen :size="36" :stroke-width="1.4" /><span>✳</span>
            </div>
            <span class="eyebrow">A LITTLE CURIOSITY GOES A LONG WAY</span>
            <h1>你的知识，<em>有问必有据。</em></h1>
            <p>从文档里寻找答案，让每一次提问都有出处。</p>
            <div class="welcome-status">
              <span class="status-dot"></span
              >{{
                readyDocs
                  ? `已连接 ${readyDocs} 份文档 · ${totalChunks} 个知识片段`
                  : "上传第一份文档，开启你的知识库"
              }}<button @click="go('documents')">
                管理文档 <ArrowUpRight :size="14" />
              </button>
            </div>
            <div class="suggestions">
              <button
                @click="
                  sendMessage('请概括知识库中现有文档的主要内容，并提供引用。')
                "
              >
                <span class="suggestion-icon"><Layers :size="19" /></span
                ><strong>快速掌握文档</strong
                ><span>梳理主要内容，找到关键信息</span
                ><ArrowUpRight :size="16" /></button
              ><button
                @click="
                  sendMessage('请从文档中找出需要重点关注的要求，并标明出处。')
                "
              >
                <span class="suggestion-icon peach"><Search :size="19" /></span
                ><strong>找到关键要求</strong
                ><span>带着问题，从原文寻找依据</span
                ><ArrowUpRight :size="16" /></button
              ><button @click="go('search')">
                <span class="suggestion-icon lilac"
                  ><FileText :size="19" /></span
                ><strong>查看检索依据</strong
                ><span>直接验证召回结果与原文片段</span
                ><ArrowUpRight :size="16" />
              </button>
            </div>
          </div>
          <div v-if="historyLoading" class="loading-state">
            <LoaderCircle class="spin" :size="22" />正在读取会话
          </div>
          <div v-else class="message-list">
            <article
              v-for="(message, index) in visibleMessages"
              :key="index"
              class="message"
              :class="message.type"
            >
              <div class="message-avatar">
                <UserRound
                  v-if="message.type === 'human'"
                  :size="17"
                /><BookOpen v-else :size="18" />
              </div>
              <div class="message-body">
                <div class="message-label">
                  {{ message.type === "human" ? "你" : "知页"
                  }}<span v-if="message.type === 'ai'">知识库助手</span>
                </div>
                <div v-if="message.type === 'human'" class="human-content">
                  {{ message.content }}
                </div>
                <div
                  v-else
                  class="markdown"
                  v-html="markdown(message.content)"
                ></div>
                <div
                  v-if="message.custom_data?.citations?.length"
                  class="citation-section"
                >
                  <span class="citation-label"
                    ><BookOpen :size="12" />参考来源 · 点击核对原文</span
                  >
                  <div class="citation-list">
                    <button
                      v-for="evidence in message.custom_data.citations"
                      :key="evidence.chunk_id"
                      @click="previewSource(evidence)"
                    >
                      <span>[{{ evidence.citation }}]</span
                      ><FileText :size="13" /><span>{{
                        evidence.document_name
                      }}</span
                      ><small>{{
                        evidence.page != null
                          ? `第 ${evidence.page} 页`
                          : `片段 ${evidence.chunk_index}`
                      }}</small
                      ><ArrowUpRight :size="13" />
                    </button>
                  </div>
                </div>
                <div v-if="message.custom_data?.degraded" class="inline-note">
                  部分检索能力暂时不可用，本次结果可能不完整。
                </div>
              </div>
            </article>
            <div v-if="streaming" class="stream-status" role="status">
              <LoaderCircle class="spin" :size="15" />{{ streamPhase
              }}<span class="pulse-dot"></span>
            </div>
            <div v-if="chatError" class="alert error" role="alert">
              {{ chatError }}
            </div>
            <div ref="chatEnd"></div>
          </div>
        </div>
        <div class="composer-wrap">
          <form class="composer" @submit.prevent="sendMessage()">
            <textarea
              v-model="draft"
              placeholder="向你的知识库提问…"
              aria-label="输入问题"
              rows="2"
              :disabled="historyLoading"
              @keydown.enter.exact="onComposerEnter"
            ></textarea>
            <div class="composer-bottom">
              <span><ShieldCheck :size="13" />仅检索你的私人知识库</span
              ><button
                v-if="streaming"
                type="button"
                class="stop-button"
                @click="controller?.abort()"
              >
                <Square :size="13" />停止等待</button
              ><button
                v-else
                class="send-button"
                :disabled="!draft.trim() || historyLoading"
                aria-label="发送问题"
              >
                <ArrowUp :size="20" />
              </button>
            </div>
          </form>
          <p class="composer-note">
            回答由 AI 基于文档生成，请结合引用核对。<span
              >Enter 发送 · Shift + Enter 换行</span
            >
          </p>
        </div>
      </main>

      <main v-else-if="page === 'documents'" class="content-page">
        <div class="page-heading">
          <div>
            <span class="section-kicker">YOUR KNOWLEDGE LIBRARY</span>
            <h1>每一份文档，都是知识的起点<span>。</span></h1>
            <p>整理你的资料，让答案从这里生长。</p>
          </div>
          <button class="button primary" @click="openUpload()">
            <Plus :size="17" />上传文档
          </button>
        </div>
        <div class="stats-grid">
          <div class="stat-card">
            <span class="stat-icon"><FolderOpen :size="21" /></span>
            <div>
              <span>文档总数</span
              ><strong>{{ documents.length }}<small>份</small></strong>
            </div>
            <span class="stat-caption">你的知识资产</span>
          </div>
          <div class="stat-card">
            <span class="stat-icon peach"><Layers :size="21" /></span>
            <div>
              <span>知识片段</span
              ><strong>{{ totalChunks }}<small>个</small></strong>
            </div>
            <span class="stat-caption">可检索的内容单元</span>
          </div>
          <div class="stat-card">
            <span class="stat-icon lilac"><Check :size="21" /></span>
            <div>
              <span>可用文档</span
              ><strong>{{ readyDocs }}<small>份</small></strong>
            </div>
            <span class="stat-caption">已完成索引</span>
          </div>
        </div>
        <section class="library-panel">
          <div class="panel-toolbar">
            <div class="panel-title">
              全部文档 <span>{{ documents.length }}</span>
            </div>
            <div class="toolbar-actions">
              <label class="search-field"
                ><Search :size="16" /><input
                  v-model="docFilter"
                  placeholder="搜索文档名称"
                  aria-label="搜索文档" /></label
              ><button
                class="icon-button"
                :disabled="docsLoading"
                aria-label="刷新文档"
                @click="loadDocs"
              >
                <RefreshCw :size="17" :class="{ spin: docsLoading }" />
              </button>
            </div>
          </div>
          <div v-if="docsLoading && !documents.length" class="loading-state">
            <LoaderCircle class="spin" :size="22" />正在读取文档
          </div>
          <div v-else-if="!visibleDocs.length" class="empty-state">
            <span class="empty-icon"
              ><FolderOpen :size="34" :stroke-width="1.3"
            /></span>
            <h3>
              {{ docFilter ? "没有找到匹配的文档" : "给你的知识一个起点" }}
            </h3>
            <p>
              {{
                docFilter
                  ? "换一个关键词试试。"
                  : "上传 PDF、Word 或文本文件，开始积累你的私人知识。"
              }}
            </p>
            <button
              v-if="!docFilter"
              class="button primary"
              @click="openUpload()"
            >
              <Upload :size="16" />上传第一份文档
            </button>
          </div>
          <div v-else class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>文档名称</th>
                  <th>状态</th>
                  <th>当前版本</th>
                  <th>片段数量</th>
                  <th class="align-right">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="doc in visibleDocs" :key="doc.id">
                  <td>
                    <button class="document-name" @click="previewDoc(doc)">
                      <span
                        class="file-icon"
                        :class="
                          doc.name.toLowerCase().endsWith('.pdf') ? 'pdf' : ''
                        "
                        ><FileText :size="20" /></span
                      ><span
                        ><strong>{{ doc.name }}</strong
                        ><small
                          >{{ doc.name.split(".").pop()?.toUpperCase() }} ·
                          {{ doc.versions.length }} 个版本</small
                        ></span
                      >
                    </button>
                  </td>
                  <td>
                    <span class="status-badge" :class="doc.status"
                      ><span></span>{{ statusLabel(doc.status) }}</span
                    >
                  </td>
                  <td>
                    <span class="version-badge">{{
                      doc.version ? `v${doc.version}` : "—"
                    }}</span>
                  </td>
                  <td class="tabular">{{ doc.chunk_count }}</td>
                  <td>
                    <div class="row-actions">
                      <button class="text-button" @click="previewDoc(doc)">
                        查看片段
                      </button>
                      <details class="action-menu">
                        <summary aria-label="更多文档操作">•••</summary>
                        <div>
                          <button
                            :disabled="!!docBusy || uploadBusy"
                            @click="openUpload(doc)"
                          >
                            <Upload :size="14" />上传新版本</button
                          ><button :disabled="!!docBusy" @click="reindex(doc)">
                            <RefreshCw
                              :size="14"
                              :class="{ spin: docBusy === doc.id }"
                            />重建索引</button
                          ><button
                            class="danger-text"
                            :disabled="!!docBusy"
                            @click="pendingDelete = doc"
                          >
                            <Trash2 :size="14" />删除文档
                          </button>
                        </div>
                      </details>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="panel-footer">
            <span><ShieldCheck :size="13" />文档仅对当前账号可见</span
            ><span>支持 PDF / DOCX / TXT / MD</span>
          </div>
        </section>
        <div class="learning-note">
          <CircleHelp :size="19" />
          <div>
            <strong>文档如何变成可检索的知识？</strong>
            <p>
              上传后，服务会解析文本、切分片段并建立索引。点击「查看片段」，可以直接核对进入知识库的内容。
            </p>
          </div>
          <ArrowUpRight :size="18" />
        </div>
      </main>

      <main v-else-if="page === 'search'" class="content-page search-page">
        <div class="page-heading">
          <div>
            <span class="section-kicker">LOOK BEHIND THE ANSWER</span>
            <h1>先看依据，再看答案<span>。</span></h1>
            <p>直接检索文档，观察哪些片段被召回，以及它们来自哪里。</p>
          </div>
          <span class="outline-tag"><Search :size="14" />检索验证</span>
        </div>
        <form class="search-box" @submit.prevent="runSearch">
          <label class="large-search"
            ><Search :size="20" /><input
              v-model="searchQuery"
              placeholder="输入问题、项目编号或关键词…"
              aria-label="检索关键词"
              required
              maxlength="2000"
          /></label>
          <div class="search-options">
            <span>混合检索 · 精排 · 引用溯源</span
            ><label
              >返回片段<select
                v-model.number="searchLimit"
                aria-label="返回片段数"
              >
                <option v-for="n in [3, 5, 10, 20]" :key="n" :value="n">
                  {{ n }}
                </option>
              </select></label
            ><button
              class="button primary"
              :disabled="searching || !searchQuery.trim()"
            >
              <LoaderCircle v-if="searching" class="spin" :size="16" /><Search
                v-else
                :size="16"
              />{{ searching ? "正在检索" : "开始检索" }}
            </button>
          </div>
        </form>
        <div v-if="searchError" class="alert error" role="alert">
          {{ searchError }}
        </div>
        <div v-if="searchResult?.degraded" class="alert">
          部分检索能力暂时不可用，当前展示服务可返回的结果。
        </div>
        <div v-if="searchResult" class="search-results">
          <div class="results-heading">
            <strong
              >检索结果 <span>{{ searchResult.results.length }}</span></strong
            ><small>分数用于相关性排序，不代表答案正确率</small>
          </div>
          <article
            v-for="(item, index) in searchResult.results"
            :key="item.chunk_id"
            class="result-card"
          >
            <div class="result-top">
              <span class="result-number">{{
                String(index + 1).padStart(2, "0")
              }}</span>
              <div>
                <strong>{{ item.document_name }}</strong
                ><span>v{{ item.version }} · {{ locationLabel(item) }}</span>
              </div>
              <button class="text-button" @click="previewSource(item)">
                查看原文<ArrowUpRight :size="14" />
              </button>
            </div>
            <p class="result-text">{{ item.text }}</p>
            <div class="result-footer">
              <span
                ><span class="tiny-dot"></span>融合分数
                {{ item.fusion_score.toFixed(4) }}</span
              ><span v-if="item.rerank_score != null"
                >精排分数 {{ item.rerank_score.toFixed(4) }}</span
              ><button
                @click="
                  draft = searchQuery;
                  go('chat');
                "
              >
                用这个问题提问 <ArrowUpRight :size="13" />
              </button>
            </div>
          </article>
          <div v-if="!searchResult.results.length" class="empty-state">
            <Search :size="32" />
            <h3>暂未找到相关片段</h3>
            <p>试试更明确的关键词，或先检查文档是否完成索引。</p>
          </div>
        </div>
        <div v-else-if="!searching" class="search-explainer">
          <span class="empty-icon"
            ><Search :size="32" :stroke-width="1.3"
          /></span>
          <h3>看看答案背后的证据</h3>
          <p>
            这里展示真实检索结果，不调用聊天模型生成回答。<br />试着用完整问题或精确编号，观察不同的匹配方式。
          </p>
          <div>
            <span>01 · 输入问题</span><ChevronRight :size="15" /><span
              >02 · 检索与排序</span
            ><ChevronRight :size="15" /><span>03 · 核对原文</span>
          </div>
        </div>
      </main>

      <main v-else class="content-page account-page">
        <div class="page-heading">
          <div>
            <span class="section-kicker">YOUR PERSONAL SPACE</span>
            <h1>账号与安全<span>。</span></h1>
            <p>管理你的登录信息与账号安全。</p>
          </div>
        </div>
        <section class="account-card">
          <div class="account-profile">
            <span class="avatar large">{{
              user.username.slice(0, 1).toUpperCase()
            }}</span>
            <div>
              <h2>{{ user.username }}</h2>
              <p>个人账号 · {{ dateLabel(user.created_at) }} 创建</p>
            </div>
            <ShieldCheck :size="25" />
          </div>
          <dl>
            <dt>用户 ID</dt>
            <dd>{{ user.id }}</dd>
            <dt>数据归属</dt>
            <dd>你的文档、知识片段与会话均归属于此账号</dd>
          </dl>
        </section>
        <section class="account-card">
          <h3>修改密码</h3>
          <p class="muted">修改成功后，所有设备需要重新登录。</p>
          <form class="password-form" @submit.prevent="changePassword">
            <label
              >当前密码<input
                v-model="currentPassword"
                type="password"
                autocomplete="current-password"
                required
                maxlength="128"
            /></label>
            <div class="form-grid">
              <label
                >新密码<input
                  v-model="newPassword"
                  type="password"
                  autocomplete="new-password"
                  required
                  minlength="8"
                  maxlength="128"
                  placeholder="8–128 位" /></label
              ><label
                >确认新密码<input
                  v-model="repeatPassword"
                  type="password"
                  autocomplete="new-password"
                  required
                  minlength="8"
                  maxlength="128"
              /></label>
            </div>
            <div v-if="accountError" class="alert error" role="alert">
              {{ accountError }}
            </div>
            <button class="button primary" :disabled="accountBusy">
              <LoaderCircle
                v-if="accountBusy"
                class="spin"
                :size="16"
              />更新密码
            </button>
          </form>
        </section>
        <div class="logout-row">
          <span>退出后，你的文档和历史会话仍会保留。</span
          ><button
            class="button secondary"
            :disabled="accountBusy"
            @click="logout"
          >
            <LogOut :size="16" />退出登录
          </button>
        </div>
      </main>
    </div>

    <div v-if="drawer" class="drawer-layer">
      <button
        class="drawer-scrim"
        aria-label="关闭原文预览"
        @click="closeDrawer"
      ></button>
      <aside
        class="source-drawer"
        v-focus-dialog="closeDrawer"
        role="dialog"
        aria-modal="true"
        aria-label="文档原文预览"
        @keydown.esc="closeDrawer"
      >
        <div class="drawer-heading">
          <div>
            <span class="section-kicker">SOURCE EXPLORER</span>
            <h2>{{ drawer === "chunks" ? "文档片段" : "引用原文" }}</h2>
          </div>
          <button
            class="icon-button"
            aria-label="关闭原文预览"
            @click="closeDrawer"
          >
            <X :size="20" />
          </button>
        </div>
        <div class="drawer-body">
          <div v-if="drawerLoading" class="loading-state">
            <LoaderCircle class="spin" :size="22" />正在读取原文
          </div>
          <div v-else-if="drawerError" class="alert error" role="alert">
            {{ drawerError }}
          </div>
          <template v-else-if="drawer === 'chunks' && selectedDoc"
            ><div class="source-document">
              <FileText :size="23" />
              <div>
                <strong>{{ selectedDoc.name }}</strong
                ><span
                  >v{{ selectedDoc.version }} ·
                  {{ selectedDoc.chunk_count }} 个片段</span
                >
              </div>
            </div>
            <div class="version-list">
              <span>版本记录</span
              ><span
                v-for="version in selectedDoc.versions"
                :key="version.id"
                class="version-badge"
                >v{{ version.number }} · {{ statusLabel(version.status) }}</span
              >
            </div>
            <article v-for="chunk in chunks" :key="chunk.id" class="chunk-card">
              <div>
                <span>片段 {{ chunk.index }}</span
                ><small
                  >{{ chunk.page != null ? `第 ${chunk.page} 页 · ` : ""
                  }}{{ chunk.characters }} 字符</small
                >
              </div>
              <p>{{ chunk.text }}</p>
            </article>
            <p v-if="!chunks.length" class="muted">此版本尚无可展示的片段。</p>
            <div class="pagination">
              <button
                class="button secondary"
                :disabled="chunkOffset === 0"
                @click="previewDoc(selectedDoc, chunkOffset - 10)"
              >
                <ChevronLeft :size="15" />上一页</button
              ><span
                >{{ chunkOffset + (chunks.length ? 1 : 0) }}–{{
                  chunkOffset + chunks.length
                }}
                / {{ selectedDoc.chunk_count }}</span
              ><button
                class="button secondary"
                :disabled="chunkOffset + 10 >= selectedDoc.chunk_count"
                @click="previewDoc(selectedDoc, chunkOffset + 10)"
              >
                下一页<ChevronRight :size="15" />
              </button></div></template
          ><template v-else-if="source"
            ><div class="source-document">
              <FileText :size="23" />
              <div>
                <strong>{{ source.document_name }}</strong
                ><span
                  >v{{ source.version }} · {{ locationLabel(source) }}</span
                >
              </div>
            </div>
            <div v-if="!source.current" class="alert">
              这条引用来自历史版本，当前文档已有更新。
            </div>
            <article class="chunk-card">
              <div><span>引用片段</span><ShieldCheck :size="14" /></div>
              <p>{{ source.text }}</p>
            </article>
            <p class="source-footnote">
              这里展示知识库中保存的文本片段，回答中的引用可以在此逐一核对。
            </p></template
          >
        </div>
      </aside>
    </div>

    <div v-if="uploadOpen" class="modal-layer">
      <div class="modal-scrim"></div>
      <section
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-title"
        v-focus-dialog="
          () => {
            if (!uploadBusy) uploadOpen = false;
          }
        "
      >
        <div class="modal-heading">
          <div>
            <span class="section-kicker">GROW YOUR KNOWLEDGE</span>
            <h2 id="upload-title">
              {{ uploadTarget ? "上传新版本" : "添加文档" }}
            </h2>
          </div>
          <button
            class="icon-button"
            aria-label="关闭上传"
            :disabled="uploadBusy"
            @click="uploadOpen = false"
          >
            <X :size="21" />
          </button>
        </div>
        <p class="muted">
          {{
            uploadTarget
              ? `为「${uploadTarget.name}」更新内容，保留历史版本。`
              : "把有价值的信息，放进你的私人知识库。"
          }}
        </p>
        <div
          class="drop-zone"
          :class="{ dragging }"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop="onDrop"
        >
          <span class="upload-symbol"><Upload :size="26" /></span
          ><strong
            >拖放文件到这里，或<button
              class="text-button"
              :disabled="uploadBusy"
              @click="fileInput?.click()"
            >
              选择文件
            </button></strong
          >
          <p>
            PDF、DOCX、TXT、MD{{
              uploadTarget ? " · 单个文件" : " · 可选择多个文件"
            }}
          </p>
          <input
            ref="fileInput"
            type="file"
            accept=".pdf,.docx,.txt,.md"
            :multiple="!uploadTarget"
            hidden
            :disabled="uploadBusy"
            @change="selectFiles(($event.target as HTMLInputElement).files)"
          />
        </div>
        <div class="upload-queue">
          <div v-for="(file, i) in uploadFiles" :key="i">
            <FileText :size="17" /><strong>{{ file.name }}</strong
            ><small>{{ (file.size / 1024).toFixed(1) }} KB</small>
          </div>
          <div
            v-for="(result, i) in uploadResults"
            :key="`result-${i}`"
            class="upload-result"
            :class="{ 'danger-text': result.failed }"
          >
            <span
              ><strong>{{ result.name }}</strong
              ><small>{{ result.state }}</small></span
            ><LoaderCircle
              v-if="uploadBusy && result.state.includes('正在')"
              :size="17"
              class="spin"
            /><Check
              v-else-if="!result.failed && result.state !== '等待处理'"
              :size="17"
            />
          </div>
        </div>
        <div class="alert subtle">
          <CircleHelp :size="16" /><span
            >文件会依次上传、解析和建立索引；相同内容会自动去重。</span
          >
        </div>
        <div class="modal-footer">
          <button
            class="button secondary"
            :disabled="uploadBusy"
            @click="uploadOpen = false"
          >
            {{ uploadResults.length ? "完成" : "取消" }}</button
          ><button
            class="button primary"
            :disabled="uploadBusy || !uploadFiles.length"
            @click="upload"
          >
            <LoaderCircle v-if="uploadBusy" class="spin" :size="16" /><Upload
              v-else
              :size="16"
            />{{ uploadBusy ? "正在建立知识索引" : "上传并建立索引" }}
          </button>
        </div>
      </section>
    </div>
    <div v-if="pendingDelete" class="modal-layer">
      <div class="modal-scrim"></div>
      <section
        class="modal small"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        v-focus-dialog="
          () => {
            if (!docBusy) pendingDelete = null;
          }
        "
      >
        <span class="delete-symbol"><Trash2 :size="24" /></span>
        <h2 id="delete-title">删除这份文档？</h2>
        <p>
          「{{
            pendingDelete.name
          }}」将退出知识库，相关索引会同步删除。此操作无法在界面中撤销。
        </p>
        <div class="modal-footer">
          <button
            class="button secondary"
            :disabled="!!docBusy"
            @click="pendingDelete = null"
          >
            取消</button
          ><button
            class="button danger"
            :disabled="!!docBusy"
            @click="deleteDoc"
          >
            <LoaderCircle v-if="docBusy" class="spin" :size="16" />确认删除
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
