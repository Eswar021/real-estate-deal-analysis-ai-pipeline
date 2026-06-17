
const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  await page.goto('file:///Users/manikantamb/_MyFiles/Work_/Freelancing/Shivam_Excel_AI_Automation/logic/output/The_Jeff_on_10th_Report_v2.html', {waitUntil: 'networkidle0'});
  await page.pdf({ path: '/Users/manikantamb/_MyFiles/Work_/Freelancing/Shivam_Excel_AI_Automation/logic/output/The_Jeff_on_10th_Report_v2.pdf', format: 'Letter', printBackground: true, margin: { top: '0px', right: '0px', bottom: '0px', left: '0px' } });
  await browser.close();
  console.log('PDF created: /Users/manikantamb/_MyFiles/Work_/Freelancing/Shivam_Excel_AI_Automation/logic/output/The_Jeff_on_10th_Report_v2.pdf');
})();
