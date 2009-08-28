/*******************************************************************************

                          The CellCognition Project
                   Copyright (c) 2006 - 2009 Michael Held
                    Gerlich Lab, ETH Zurich, Switzerland

            CellCognition is distributed under the LGPL license.
                      See the LICENSE.txt for details.
               See trunk/AUTHORS.txt for author contributions.

*******************************************************************************/

// Author(s): Michael Held
// $Date$
// $Rev$
// $URL: https://svn.cellcognition.org/mito/trunk/include/mito/reader/wrap_lsm#$


// forward declarations:
void wrap_renderer();
void wrap_lut();

namespace cecog {
  namespace python {

    void wrap_cecog()
    {
      wrap_renderer();
      wrap_lut();
    }

  } // namespace python

} // namespace cecog