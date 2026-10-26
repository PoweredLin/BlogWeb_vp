import {defineComponent, Fragment, h, render} from 'vue';

// Preserve the established templates while Vue owns and diffs the tool DOM.
// No browser template compiler or eval; text is already escaped by the view helpers.
// Event handlers remain delegated by app.js, including dialogs outside #app.
function nodes(markup) {
  const template=document.createElement('template');
  template.innerHTML=markup;
  const convert=node=>{
    if(node.nodeType===Node.TEXT_NODE) return node.textContent;
    if(node.nodeType!==Node.ELEMENT_NODE) return null;
    const props={};
    for(const {name,value} of node.attributes) {
      if(/^on/i.test(name)) continue;
      props[name]=['checked','selected','disabled','multiple','readonly','required','open'].includes(name)?true:value;
    }
    if(props['data-id']) props.key=node.tagName+':'+props['data-id'];
    return h(node.tagName.toLowerCase(),props,[...node.childNodes].map(convert));
  };
  return [...template.content.childNodes].map(convert);
}
const ToolsPage=defineComponent({
  name:'LifeToolsPage',
  props:{markup:{type:String,required:true}},
  setup(props){return ()=>h(Fragment,null,nodes(props.markup));}
});
export function renderTools(root,markup){render(h(ToolsPage,{markup}),root);}
