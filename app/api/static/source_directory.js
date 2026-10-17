/* Zero-network source explorer for server-rendered registry metadata. */
(function () {
  "use strict";
  const root=document.querySelector(".coverage-explorer");
  if(!root)return;
  const input=root.querySelector("#coverageSearch");
  const buttons=Array.from(root.querySelectorAll("[data-coverage-region]"));
  const groups=Array.from(root.querySelectorAll("[data-coverage-group]"));
  const empty=root.querySelector("#coverageNoMatches");
  const counter=root.querySelector("#coverageCounter");
  let active="all";
  function update(){
    const q=input.value.trim().toLocaleLowerCase().slice(0,100);
    let visible=0;
    for(const group of groups){
      const regionAllowed=active==="all"||group.dataset.coverageGroup===active;
      let groupVisible=0;
      for(const card of group.querySelectorAll(".coverage-card")){
        const matches=regionAllowed&&(!q||(card.dataset.sourceSearch||"").includes(q));
        card.hidden=!matches;
        if(matches){visible++;groupVisible++;}
      }
      group.hidden=!groupVisible;
    }
    empty.hidden=visible>0 || groups.length===0;
    counter.textContent=String(visible)+" / "+String(root.querySelectorAll(".coverage-card").length);
  }
  buttons.forEach(button=>button.addEventListener("click",()=>{
    active=button.dataset.coverageRegion||"all";
    buttons.forEach(item=>{
      const selected=item===button;
      item.classList.toggle("is-selected",selected);
      item.setAttribute("aria-pressed",String(selected));
    });
    update();
  }));
  input.addEventListener("input",update);
  update();
})();
