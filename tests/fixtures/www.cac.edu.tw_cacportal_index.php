<!doctype html>
<html lang="zh-TW">
<head>
<meta charset="utf-8"> 
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes, minimum-scale=0.1,maximum-scale=5.0" />
<!--[if lte IE 8]>
  <link rel="stylesheet" type="text/css" href="css/portal_ie8.css?V1.2">
<![endif]-->
<link rel="icon" href="https://www.cac.edu.tw/favicon.ico" type="image/x-icon" />
<link rel="Bookmark" href="https://www.cac.edu.tw/favicon.ico" type="image/x-icon" />
<link rel="apple-touch-icon" href="https://www.cac.edu.tw/apple_touch_icon.png" />




  
  <!--[if lte IE 8]>
    <link rel="stylesheet" type="text/css" href="css/portal_ie8.css?V1.2">
  <![endif]-->
  <link rel="stylesheet" type="text/css" href="css/portal_mobile.css?V1.2" media="screen and (max-width: 784px)">
  <link rel="stylesheet" type="text/css" href="css/portal_pc.css?V1.2" media="screen and (min-width: 785px) ">    

<title>大學甄選入學委員會首頁</title>
<meta name="keywords" content="大學甄選,甄選入學,申請入學,個人申請,繁星推薦,甄選入學委員會,大學甄選入學委員會,高中升學,高職升學,多元入學" />
<script type="text/javascript" src="https://ajax.googleapis.com/ajax/libs/jquery/3.7.1/jquery.min.js"></script>
<script>   if (!window.jQuery) { 
	document.write('<script src="jquery/jquery-3.7.1.min.js"><\/script>'); 	
	}                                   
</script> 

<script type="text/javascript"> 
	
		function isMobile() {
    try{ document.createEvent("TouchEvent"); return true; }
    catch(e){ return false;}
  }
	
	function resize_win(){				
	  var first_x=document.documentElement.clientWidth;
	  var first_y=document.documentElement.clientHeight;
	  if(first_y <= 450)	{first_y = 450;}	  
	  
	  //var main_pic_width  = $('#portal_main_pic').width();
	  //var main_pic_height = $('#portal_main_pic').height();
  
    var l_logowidth, l_logoheight, logo_position, l_logo_y;
    var l_mainboxtop, l_mainboxwidth, l_mainboxheight, l_mainboxleft; 
    var l_precount_height;
    var l_picwidth, l_picheight, l_pictop; 
    var l_balloonwidth, l_balloonheight; 
    var l_startop, l_starleft, l_starwidth, l_starheight;
    var l_applytop, l_applyleft, l_applywidth, l_applyheight;
    var l_decltextheight;   
    var l_portal_page_box_height;
    /*
    if(first_x>768){    	
      new_first_y = first_y; 
    }else{
    	new_first_y = first_y + 0; 
    }
    */
    
    
    
    
    $(function(){
    	l_portal_page_box_height = first_y;
    	      
            $("#portal_page_box").css({   
        height: l_portal_page_box_height+"px",
      });
          
      if(first_x>=768){
      	      	if(first_x >= first_y){      		
      		l_logoheight = first_y*0.093333;          
      	}
      	if(first_x < first_y){      		
      		l_logoheight = first_x*0.093333;          
      	}      	      	        
      	l_logowidth = l_logoheight*8.732143;
      }else{
      	l_logoheight = first_y*0.093333;
        l_logowidth = first_x*0.8;
      }
              
      $("#portal_logo").css({ 
      	width: l_logowidth +"px",      	
      	height: l_logoheight +"px",
      });
      
              
                                           
      if(first_x>=768){
      	      	
      	if(first_x >= first_y){
      		l_mainboxheight = first_y*0.6975;
      		l_picheight = first_y*0.430833;       		
      		l_balloonheight = first_y*0.6975; 
      		l_decltextheight = first_y*0.020833;          
      	}
      	if(first_x < first_y){ 
      		l_mainboxheight = first_x*0.6975;     	
      		l_picheight = first_x*0.430833;     
      		l_balloonheight = first_x*0.6975;      
      		l_decltextheight = first_x*0.020833;
      	}
      	
      	l_mainboxwidth = l_mainboxheight * 1.168459;
      	l_picwidth = l_picheight*0.773694;
      	l_balloonwidth = l_balloonheight*0.753883;
      	
      	l_pictop = (l_mainboxheight - l_picheight) / 2;
      	
      	l_startop = l_picheight * 0.586074;
        l_starleft = l_picwidth * 0.0325;
        l_starwidth = l_picwidth * 0.925;
        l_starheight = l_picheight * 0.164410;
        
        l_applytop = l_picheight * 0.798839;
        l_applyleft = l_starleft;
        l_applywidth = l_starwidth;
        l_applyheight = l_starheight;
        
      }else{
      	l_mainboxheight = first_y* 0.7;
      	l_picheight = first_y* 0.64625;
      	
        l_mainboxwidth = l_mainboxheight * 0.714286;
        l_picwidth = l_picheight* 0.773694;
        
        l_pictop = l_mainboxheight - l_picheight;
                
        l_startop = l_picheight * 0.586074;
        l_starleft = l_picwidth * 0.0325;
        l_starwidth = l_picwidth * 0.925;
        l_starheight = l_picheight * 0.164410;
        
        l_applytop = l_picheight * 0.798839;
        l_applyleft = l_starleft;
        l_applywidth = l_starwidth;
        l_applyheight = l_starheight;
        
      }                     
              
            logo_position = $('#portal_logo').offset();  
      l_logo_y = logo_position.top;      
      decltext_position = $('#portal_page_decltext').offset();  
      l_decltext_y = logo_position.top;  
            l_precount_height = l_logo_y + l_logoheight + l_decltext_y;     
      l_mainboxtop = ((first_y - l_precount_height - l_mainboxheight) / 2) ;                  
      l_mainboxleft = (first_x - l_mainboxwidth) / 2;    
      $("#portal_main_box").css({ 
      	top: l_mainboxtop + "px", 
      	width: l_mainboxwidth + "px",
        height: l_mainboxheight +"px",             
        left:l_mainboxleft + "px", 
      });
                     
      $("#portal_main_pic").css({       	
        top: l_pictop + "px",
      	width: l_picwidth + "px",
        height: l_picheight +"px",        
      });
            
      $("#portal_main_balloon").css({   
      	width: l_balloonwidth + "px",
        height: l_balloonheight +"px",      
      });
                         
      $("#portal_starlink").css({ 
      	top: l_startop + "px",
      	left:l_starleft + "px", 
      	width: l_starwidth + "px",
        height: l_starheight +"px",
      });
      
      $("#portal_applylink").css({ 
      	top: l_applytop + "px",
      	left:l_applyleft + "px", 
      	width: l_applywidth + "px",
        height: l_applyheight +"px",
      });
      
      $("#portal_page_decltext").css("line-height", l_decltextheight +"px");
                   
    });	 //  end-$(function(){
			
  }	// end-function resize_win()
    
  //第一次進來時，先檢查一次
	resize_win();

  		
	$(document).ready(function(){		
	  var screen_x=document.documentElement.clientWidth;   
    var ua = navigator.userAgent;  
  
        if(screen_x < 768)  
    {   	
      if((ua.indexOf('iPhone') > 0 && ua.indexOf('iPad') == -1)
         || ua.indexOf('iPod') > 0
         || ua.indexOf('Android') > 0
         || (ua.indexOf('Mobile') > 0 && ua.indexOf('iPad') == -1)
         || ua.indexOf('Windows Phone') > 0 
         || isMobile()
      ){ 	    	
	    		      $("div#portal_starlink_box a").attr("href", "../mobile_star116/index.php");
	      $("div#portal_applylink_box a").attr("href", "../mobile_apply116/index.php");
	      	    }	
    }
		
	  $(window).resize(function(){	
	  
	 
      
      	    	    //----------------
	    
	    
	    
      //之後螢幕解析度有改變時，就再檢查一次
      resize_win();	
	     
    });   
  });
		
</script>



 
<!-- Global site tag (gtag.js) - Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-X90GJM2RNE"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-X90GJM2RNE');
</script>





<script>NS_CSM_td=275629314;NS_CSM_pd=275116667;NS_CSM_u="/clm10";NS_CSM_col="AAAAAAVzcHsmMtr6Pt6moMTApcDFrEQVzq5nlo6ekGZfIMuAW367S+AF5weU33SR4P9wcQqlv4yFIRHuaEs4Jpipx7jr";</script><script type="text/javascript">function sendTimingInfoInit(){setTimeout(sendTimingInfo,0)}function sendTimingInfo(){var wp=window.performance;if(wp){var c1,c2,t;c1=wp.timing;if(c1){var cm={};cm.ns=c1.navigationStart;if((t=c1.unloadEventStart)>0)cm.us=t;if((t=c1.unloadEventEnd)>0)cm.ue=t;if((t=c1.redirectStart)>0)cm.rs=t;if((t=c1.redirectEnd)>0)cm.re=t;cm.fs=c1.fetchStart;cm.dls=c1.domainLookupStart;cm.dle=c1.domainLookupEnd;cm.cs=c1.connectStart;cm.ce=c1.connectEnd;if((t=c1.secureConnectionStart)>0)cm.scs=t;cm.rqs=c1.requestStart;cm.rss=c1.responseStart;cm.rse=c1.responseEnd;cm.dl=c1.domLoading;cm.di=c1.domInteractive;cm.dcls=c1.domContentLoadedEventStart;cm.dcle=c1.domContentLoadedEventEnd;cm.dc=c1.domComplete;if((t=c1.loadEventStart)>0)cm.ls=t;if((t=c1.loadEventEnd)>0)cm.le=t;cm.tid=NS_CSM_td;cm.pid=NS_CSM_pd;cm.ac=NS_CSM_col;var xhttp=new XMLHttpRequest();if(xhttp){var JSON=JSON||{};JSON.stringify=JSON.stringify||function(ob){var t=typeof(ob);if(t!="object"||ob===null){if(t=="string")ob='"'+ob+'"';return String(ob);}else{var n,v,json=[],arr=(ob&&ob.constructor==Array);for(n in ob){v=ob[n];t=typeof(v);if(t=="string")v='"'+v+'"';else if(t=="object"&&v!==null)v=JSON.stringify(v);json.push((arr?"":'"'+n+'":')+String(v));}return(arr?"[":"{")+String(json)+(arr?"]":"}");}};xhttp.open("POST",NS_CSM_u,true);xhttp.send(JSON.stringify(cm));}}}}if(window.addEventListener)window.addEventListener("load",sendTimingInfoInit,false);else if(window.attachEvent)window.attachEvent("onload",sendTimingInfoInit);else window.onload=sendTimingInfoInit;</script></head>

<body>

<div id="portal_page_box">	  			
	<div class="portal_top_text">大學招生委員會聯合會</div>
  <div class="portal_separate portal_position_rel"></div> 
          
    <div id="portal_logo"></div>
  <div id="portal_logo_ie8"></div>      
      
  <div id="portal_main_box">  	  	
    <div id="portal_main_pic"> 
    	<div id = "portal_starlink_box">
    	  <a href="../star116/index.php"><div id="portal_starlink"></div></a>
      </div>
      <div id = "portal_applylink_box">
    	  <a href="../apply116/index.php"><div id="portal_applylink"></div></a>    	
    	</div>
    </div>    
    <div id="portal_main_balloon"></div>      
  </div>
  
    
  
    
  <div id="portal_main_box_ie8">  	  	    
    <div id="portal_main_pic_ie8">
      <a href="../star116/index.php"><div id="portal_starlink_ie8"></div></a>
      <a href="../apply116/index.php"><div id="portal_applylink_ie8"></div></a>    
    </div>  
  </div>               
    
  <div id="portal_page_decltext"> 
  	<div id="portal_browser_text">  		
  	  建議瀏覽環境：Chrome、FireFox、Edge
  	</div>   	
  	<div id="portal_separate_bottom" class="portal_separate"></div>	  	
    621301嘉義縣民雄鄉大學路一段168號    
    <br>Copyright by CAC. All rights reserved.
    &nbsp;&nbsp;<a href="https://www.cac.edu.tw/cacportal/PIMS_PrivateStatement/PIMS_PS_readfile.php?fileid1=CAC1001&fileid2=new" target="_blank">隱私權聲明</a>
  </div>  
     
</div>





</body>
</html>
