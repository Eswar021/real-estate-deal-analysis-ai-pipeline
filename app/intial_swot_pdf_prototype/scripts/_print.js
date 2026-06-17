const puppeteer = require('puppeteer');
(async () => {
  const b = await puppeteer.launch();
  const p = await b.newPage();
  await p.goto('file:///Users/manikantamb/_MyFiles/Work_/Freelancing/Shivam_Excel_AI_Automation/logic/output/PIR_The_Jeff_on_10th_Jeffersonville_April_09__2026.html', {waitUntil: 'networkidle0'});
  await p.pdf({ path: '/Users/manikantamb/_MyFiles/Work_/Freelancing/Shivam_Excel_AI_Automation/logic/output/PIR_The_Jeff_on_10th_Jeffersonville_April_09__2026.pdf', format: 'Letter', printBackground: true, margin: { top:'0px',right:'0px',bottom:'0px',left:'0px' } });
  await b.close();
  console.log('PDF: /Users/manikantamb/_MyFiles/Work_/Freelancing/Shivam_Excel_AI_Automation/logic/output/PIR_The_Jeff_on_10th_Jeffersonville_April_09__2026.pdf');
})();