import { defineStore } from "pinia"; //引入pinia
// _setLocalItem 封装的缓存本地的方法 remove和get分别对应缓存的删除和获取
import { _getLocalItem, _setLocalItem } from "@/utils/tool";

// 本地数据加密解密
import { _encrypt, _decrypt } from "@/utils/encipher";

// 可以去看看vueUse怎么使用useDark 这个可以快速切换主题
import { useDark, useToggle } from "@vueuse/core";

const isDark = useDark({
  // 存储到localStorage/sessionStorage中的Key 根据自己的需求更改
  storageKey: "useDarkKEY",
  // 暗黑class名字
  valueDark: "dark",
  // 高亮class名字
  valueLight: "light",
});
const toggle = useToggle(isDark);

export const staticData = defineStore("staticData", {
  // 数据存到store里刷新页面会重置，持久化就不会了
  persist: {
    enabled: true, //开启数据持久化
    strategies: [
      {
        key: "staticState", //给一个要保存的名称
        storage: localStorage, //sessionStorage / localStorage 存储方式
      },
    ],
  },
  state: () => {
    return {
      // md预览主题列表
      previewThemeList: ["default", "github", "vuepress", "mk-cute", "smart-blue", "cyanosis"],
      // md代码主题列表
      codeThemeList: [
        "atom",
        "a11y",
        "github",
        "gradient",
        "kimbie",
        "paraiso",
        "qtcreator",
        "stackoverflow",
      ],
      // md预览主题
      previewTheme: "default",
      // md代码主题
      codeTheme: "atom",
      // 整体主题 黑夜和白天
      theme: isDark.value,
      // 头部图片地址
      pageHeaderList: [],
      messageTypeIsCard: false,
    };
  },
  getters: {
    // 获取当前整体主题 黑夜/白天
    mainTheme() {
      return isDark.value;
    },
    // 获取每个页面背景图
    getPageHeaderList() {
      return this.pageHeaderList || _getLocalItem("pageHeaderList");
    },
    getMessageTypeIsCard() {
      return this.messageTypeIsCard;
    },
  },
  actions: {
    // 切换主题
    switchMainTheme() {
      toggle();
      this.theme = isDark.value;
      _setLocalItem("mainTheme", this.theme ? "dark" : "light");
    },
    // 缓存图片
    setPageHeaderLIst(list) {
      this.pageHeaderList = list;
      _setLocalItem("pageHeaderList", list);
    },
    setMessageTypeIsCard(type) {
      this.messageTypeIsCard = type;
    },
  },
});

export const user=defineStore('user',{state:()=>({blogAvatar:'/favicon.svg',userInfo:{},showLogin:false}),getters:{getBlogAvatar:s=>s.blogAvatar,getUserInfo:s=>s.userInfo,getToken:()=>'',getShowLogin:s=>s.showLogin},actions:{setBlogAvatar(v){this.blogAvatar=v;},setUserInfo(v){this.userInfo=typeof v==='string'?JSON.parse(v):v;},setToken(){},clearUserInfo(){this.userInfo={};},setShowLogin(v){if(v)location.href='/login';this.showLogin=false;}}});
